"""AI face scan for the Add person page (Đức Mạnh's innovative feature). Replaces the manual photo upload.

A scan session collects the best face stills for 5 head poses (SLOTS), PER_SLOT each. Every frame, from the live
camera (POST /api/enrol/frame) or sampled from an uploaded video (POST /api/enrol/video), goes through analyse():

    YuNet face + 5 landmarks -> head pose (yaw, pitch) from the landmarks -> which slot it fits
    face quality: ml/face_quality (trained model; heuristic fallback when face_quality.pt is missing)
    liveness: ml/anti_spoofing, averaged over the session's recent crops (one crop is too noisy)
    glasses: ml/glasses_detection (recorded in scan.json)

and gets a hint for the person ("turn left", "move closer", ...). A still is kept when there is exactly one face, it
is large and well lit, the session looks live, and its quality passes the model's threshold; each slot keeps the
PER_SLOT best. Kept stills are checked against the registered faces (duplicate warning, never a block).

POST /api/students with enrol_session=<id> saves the kept stills into data/photos/<id>/ with scan.json.
Sessions live in memory and expire after SESSION_TTL seconds. Heavy imports (cv2, models) happen inside functions.
"""
import json
import math
import threading
import time
import uuid
from datetime import datetime

import numpy as np

SLOTS = {   # name -> (yaw range, pitch range) in degrees, named from the PERSON's side (what the hints say):
    "front": ((-10, 10), (-10, 10)),      # yaw > 0 = nose towards the image right = head turned to the person's left
    "left": ((15, 45), (-15, 15)),        # pitch < 0 = chin up
    "right": ((-45, -15), (-15, 15)),
    "up": ((-12, 12), (-40, -8)),
    "down": ((-12, 12), (8, 40)),
}
PER_SLOT = 3
MIN_FACE_PX = 110           # face box height in the full-resolution still (phone / 1080p)
MIN_FACE_PX_LOW = 80        # for a 720p (or smaller) camera
BRIGHTNESS = (60, 200)      # mean grey level of the face crop
SECOND_FACE_RATIO = 0.5    # another face this big (vs the largest) refuses the frame
MIN_POSE_GAP = 4.0          # degrees: stills of one slot must differ this much in yaw or pitch (else the better one stays)
LIVENESS_WINDOW = 10        # crops averaged for liveness
SESSION_TTL = 30 * 60
FAIL_LOG = None             # logs/enrol_failures.jsonl in the repo when None (tests point it elsewhere)
VIDEO_FPS = 5.0
VIDEO_MAX_S = 60
VIDEO_MAX_BYTES = 300 * 2**20
# The weights carry 0.78, chosen on Kaggle 64 px crops (03_evaluate.ipynb). Real webcam frames score lower
# (median 0.67-0.75 on the team's AppliedML photos), so the scan uses a threshold calibrated on those photos.
QUALITY_THRESHOLD_WEBCAM = 0.65

_lock = threading.Lock()
_sessions = {}


# ---- models -------------------------------------------------------------------------------------------------

def _infer(feature):
    from ..core.ml_models import load_infer
    return load_infer(feature)


def quality_model():
    """(scorer, threshold, name): the trained model when its weights exist, else the heuristic baseline."""
    from ..core.ml_models import weights_file
    if weights_file("face_quality").is_file():
        q = _infer("face_quality")
        return q.score, QUALITY_THRESHOLD_WEBCAM, "face_quality"
    return None, 0.35, "heuristic"


def _heuristic():
    import importlib.util
    from ..core.ml_models import ML_DIR
    spec = importlib.util.spec_from_file_location("hawkeye_ml_face_quality_heuristic", ML_DIR / "face_quality" / "heuristic.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_heur = None


def heuristic(crop, face_px, yaw, pitch):
    global _heur
    if _heur is None:
        _heur = _heuristic()
    return _heur.heuristic_score(crop, face_px, yaw, pitch)


# ---- geometry ---------------------------------------------------------------------------------------------

def head_pose(marks):
    """Rough yaw / pitch in degrees from YuNet's 5 landmarks (right eye, left eye, nose, mouth right, mouth left).
    yaw: nose offset from the eye midpoint, relative to the eye distance; pitch: nose height between the eye line
    and the mouth line (about 0.5 when level). Good enough to sort frames into pose slots."""
    (rex, rey), (lex, ley), (nx, ny), (rmx, rmy), (lmx, lmy) = marks
    ex, ey = (rex + lex) / 2, (rey + ley) / 2
    eye_dist = math.hypot(lex - rex, ley - rey) or 1.0
    mx, my = (rmx + lmx) / 2, (rmy + lmy) / 2
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, 2.2 * (nx - ex) / eye_dist))))
    face_h = (my - ey) or 1.0
    pitch = (((ny - ey) / face_h) - 0.55) * 120
    return round(yaw, 1), round(pitch, 1)


def slot_for(yaw, pitch):
    for name, ((y0, y1), (p0, p1)) in SLOTS.items():
        if y0 <= yaw <= y1 and p0 <= pitch <= p1:
            return name
    return None


def _hint(missing, yaw, pitch):
    """Tell the person how to reach the first missing slot (their own left / right). Each hint names that slot, and
    overshooting it says "a little less", so "turn back" is never mistaken for "now do the other side"."""
    if not missing:
        return "done"
    target = missing[0]
    (y0, y1), (p0, p1) = SLOTS[target]
    if target == "front":
        return "look straight at the camera" if not (y0 <= yaw <= y1 and p0 <= pitch <= p1) else "hold still"
    if target in ("left", "right"):
        if not p0 <= pitch <= p1:
            return f"{target} side: keep your chin level"
        far = yaw > y1 if target == "left" else yaw < y0          # past the slot, away from the camera
        if far:
            return f"{target} side: a little less, turn back slightly"
        if y0 <= yaw <= y1:
            return "hold still"
        return f"{target} side: turn your head to your {target}" + (" a bit more" if (yaw > 5 if target == "left" else yaw < -5) else "")
    # up / down
    if not y0 <= yaw <= y1:
        return f"chin {target}: face the camera first"
    far = pitch < p0 if target == "up" else pitch > p1
    if far:
        return f"chin {target}: a little less"
    if p0 <= pitch <= p1:
        return "hold still"
    return f"chin {target}: tilt your chin {target}" + (" a bit more" if (pitch < -3 if target == "up" else pitch > 3) else "")


# ---- sessions ---------------------------------------------------------------------------------------------

def new_session(source="live"):
    _expire()
    sid = uuid.uuid4().hex[:16]
    with _lock:
        _sessions[sid] = {"id": sid, "source": source, "created": time.time(), "slots": {k: [] for k in SLOTS},
                          "crops": [], "liveness": None, "duplicate": None, "frames": 0, "failed": None}
    return sid


def get(sid):
    _expire()
    with _lock:
        s = _sessions.get(sid)
    if s is None:
        raise KeyError(sid)
    return s


def drop(sid):
    with _lock:
        _sessions.pop(sid, None)


def _expire():
    now = time.time()
    with _lock:
        for k in [k for k, s in _sessions.items() if now - s["created"] > SESSION_TTL]:
            del _sessions[k]


def missing_slots(s):
    return [k for k in SLOTS if len(s["slots"][k]) < PER_SLOT]


def summary(s):
    _, thr, model = quality_model()
    return {"session_id": s["id"], "source": s["source"], "model": model, "threshold": round(thr, 4),
            "per_slot": PER_SLOT, "missing": missing_slots(s), "done": not missing_slots(s),
            "liveness": s["liveness"], "duplicate": s["duplicate"], "frames": s["frames"], "failed": s.get("failed"),
            "slots": {k: [_public(e) for e in v] for k, v in s["slots"].items()}}


def fail(s, reason, attempts, reasons=None):
    """Mark the scan failed (the page gave up after `attempts` attempts) and append it to logs/enrol_failures.jsonl."""
    import json
    s["failed"] = {"reason": reason, "attempts": attempts, "reasons": reasons or {},
                   "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
    entry = {"session_id": s["id"], "source": s["source"], "frames": s["frames"],
             "kept": sum(len(v) for v in s["slots"].values()), "missing": missing_slots(s), **s["failed"]}
    log = FAIL_LOG or _repo_dir() / "logs" / "enrol_failures.jsonl"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # logging must not break the scan
    return entry


def _repo_dir():
    from ..config import REPO_DIR
    return REPO_DIR


def _public(e):
    return {k: v for k, v in e.items() if k not in ("jpeg", "crop")}


# ---- analysis ---------------------------------------------------------------------------------------------

def analyse(s, image, final=False, t=None):
    """Analyse one BGR frame for session s. final=True: keep it in its slot if it passes. t = video time (s)."""
    import cv2
    from ..core.ml_models import crop_face
    from ..pipeline.detector import detect_faces_landmarks

    h, w = image.shape[:2]
    s["frames"] += 1
    out = {"faces": 0, "accepted": False, "kept": False, "frame_size": [w, h], "t": t}
    faces = detect_faces_landmarks(image, min_size=24)
    out["faces"] = len(faces)
    # people far behind (a classroom) are ignored; a second face at least half the size means someone close by
    if faces:
        faces = [f for f in faces if f[3] >= SECOND_FACE_RATIO * faces[0][3]]
    missing = missing_slots(s)
    if not faces:
        return {**out, "hint": "no face: look at the camera", "reason": "no_face"}
    if len(faces) > 1:
        return {**out, "hint": "only one person in the frame", "reason": "several_faces"}
    x, y, bw, bh, conf, marks = faces[0]
    yaw, pitch = head_pose(marks)
    crop = crop_face(image, (x, y, bw, bh), "face_quality")
    grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    bright = float(grey.mean())
    scorer, thr, model = quality_model()
    q = float(scorer(crop)) if scorer else heuristic(crop, bh, yaw, pitch)
    slot = slot_for(yaw, pitch)

    live_crop = crop_face(image, (x, y, bw, bh), "anti_spoofing")
    s["crops"] = (s["crops"] + [live_crop])[-LIVENESS_WINDOW:]
    if final or len(s["crops"]) % 3 == 0:            # liveness every 3rd preview frame and on every still
        try:
            s["liveness"] = {k: (round(v, 4) if isinstance(v, float) else v)
                             for k, v in _infer("anti_spoofing").check(s["crops"]).items()}
        except Exception as e:  # noqa: BLE001 - missing weights must not stop the scan; reported instead
            s["liveness"] = {"live": None, "score": None, "error": str(e)}
    out.update(box=[round(x / w, 4), round(y / h, 4), round(bw / w, 4), round(bh / h, 4)],
               landmarks=[[round(px / w, 4), round(py / h, 4)] for px, py in marks],
               yaw=yaw, pitch=pitch, slot=slot, quality=round(q, 4), model=model, threshold=round(thr, 4),
               brightness=round(bright, 1), face_px=round(bh), liveness=s["liveness"])

    # full-resolution stills from a 720p camera are smaller: same flow, lower size floor
    min_px = MIN_FACE_PX if max(w, h) >= 1280 and min(w, h) > 720 else MIN_FACE_PX_LOW
    if (s["liveness"] or {}).get("live") is False:
        reason, hint = "not_live", "use a real face (photos and screens are refused)"
    elif bright < BRIGHTNESS[0]:
        reason, hint = "too_dark", "too dark: move to a brighter place"
    elif bright > BRIGHTNESS[1]:
        reason, hint = "too_bright", "too bright or back-lit: face the light"
    elif bh < min_px:
        reason, hint = "too_small", "move closer"
    elif slot is None:
        reason, hint = "between_poses", _hint(missing, yaw, pitch)
    elif q < thr:
        reason, hint = "low_quality", "hold still (image not sharp enough)"
    else:
        reason = "ok"
        hint = "hold still" if slot in missing else _hint(missing, yaw, pitch)
    out.update(reason=reason, hint=hint, accepted=reason == "ok")

    if final and out["accepted"]:
        out["kept"] = _keep(s, slot, image, crop, out, glasses_of(crop))
        if out["kept"] and s["duplicate"] is None:
            s["duplicate"] = duplicate_of(crop)
        missing = missing_slots(s)
        out["hint"] = "done" if not missing else _hint(missing, yaw, pitch)
    out.update(missing=missing_slots(s), done=not missing_slots(s), duplicate=s["duplicate"])
    return out


def glasses_of(crop):
    try:
        r = _infer("glasses_detection").predict(crop)
        return {"glasses": bool(r["glasses"]), "score": round(float(r["glasses_score"]), 4)}
    except Exception:  # noqa: BLE001
        return None


def duplicate_of(crop):
    """{student_id, name, score} when the face already matches a registered student, else False."""
    try:
        from . import gallery
        rec = _infer("face_recognition")
        faces, names = gallery.registered_faces()
        if not faces:
            return False
        sid, score = rec.identify(crop, faces, rec.threshold())
        return {"student_id": sid, "name": names.get(sid, sid), "score": round(float(score), 4)} if sid else False
    except Exception:  # noqa: BLE001
        return None


def _keep(s, slot, image, crop, info, glasses):
    import cv2
    entries = s["slots"][slot]
    near = [e for e in entries if abs(e["yaw"] - info["yaw"]) < MIN_POSE_GAP and abs(e["pitch"] - info["pitch"]) < MIN_POSE_GAP]
    if near and info["quality"] <= max(e["quality"] for e in near):
        return False                 # nearly the same view as a better kept still
    if not near and len(entries) >= PER_SLOT and info["quality"] <= min(e["quality"] for e in entries):
        return False
    ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    entry = {"slot": slot, "quality": info["quality"], "yaw": info["yaw"], "pitch": info["pitch"],
             "face_px": info["face_px"], "brightness": info["brightness"], "frame_size": info["frame_size"],
             "liveness": (s["liveness"] or {}).get("score"), "glasses": glasses,
             "t": info.get("t"), "jpeg": jpeg.tobytes()}
    with _lock:
        for e in near:
            entries.remove(e)
        entries.append(entry)
        entries.sort(key=lambda e: -e["quality"])
        del entries[PER_SLOT:]
    return entry in entries


def still_jpeg(s, slot, index):
    return s["slots"][slot][index]["jpeg"]


# ---- video ------------------------------------------------------------------------------------------------

def frames_from_video(path, fps=VIDEO_FPS, max_s=VIDEO_MAX_S):
    """Yield (t, BGR frame) about fps times a second. Phone videos in HEVC that OpenCV cannot read are converted
    with the system ffmpeg first."""
    import cv2
    cap = cv2.VideoCapture(str(path))
    ok, frame = cap.read() if cap.isOpened() else (False, None)
    if not ok:
        cap.release()
        path = _ffmpeg_to_mp4(path)
        cap = cv2.VideoCapture(str(path))
        ok, frame = cap.read()
        if not ok:
            raise ValueError("cannot read this video (try MP4 / H.264)")
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    src_fps = src_fps if 1 <= src_fps <= 240 else 30.0      # browser .webm reports 1000 fps
    step = max(1, round(src_fps / fps))
    i = 0
    while ok:
        t = i / src_fps
        if t > max_s:
            break
        if i % step == 0:
            yield t, frame
        ok, frame = cap.read()
        i += 1
    cap.release()


def _ffmpeg_to_mp4(path):
    import shutil
    import subprocess
    exe = shutil.which("ffmpeg")
    if not exe:
        raise ValueError("this video needs FFmpeg to be decoded (install it: winget install Gyan.FFmpeg)")
    out = path.with_suffix(".h264.mp4")
    subprocess.run([exe, "-y", "-loglevel", "error", "-i", str(path), "-t", str(VIDEO_MAX_S), "-an", "-c:v",
                    "libx264", "-preset", "veryfast", "-crf", "16", str(out)], check=True, timeout=300)
    return out


def scan_video(s, path):
    """Run every sampled frame of a video through analyse(final=True)."""
    counts = {}
    for t, frame in frames_from_video(path):
        r = analyse(s, frame, final=True, t=round(t, 2))
        counts[r["reason"]] = counts.get(r["reason"], 0) + 1
        if r["done"]:
            break
    return counts


# ---- saving -----------------------------------------------------------------------------------------------

def save(s, folder):
    """Write the kept stills to folder (photo_01.jpg ...) and scan.json; returns the number of photos."""
    from ..core.ml_models import weights_file
    versions = {}
    try:
        from ..config import REPO_DIR
        versions = json.loads((REPO_DIR / "ml" / "model_versions.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    _, thr, model = quality_model()
    images, n = [], 0
    for slot in SLOTS:
        for e in s["slots"][slot]:
            n += 1
            name = f"photo_{n:02d}.jpg"
            (folder / name).write_bytes(e["jpeg"])
            images.append({"file": name, **_public(e)})
    scan = {"source": s["source"], "saved_at": datetime.now().isoformat(timespec="seconds"),
            "quality_model": model, "threshold": thr, "per_slot": PER_SLOT, "slots": list(SLOTS),
            "missing": missing_slots(s), "liveness": s["liveness"], "duplicate": s["duplicate"],
            "frames_analysed": s["frames"],
            "model_versions": {k: versions.get(k, {}).get("version") for k in
                               ("face_quality", "face_recognition", "anti_spoofing", "glasses_detection")},
            "quality_weights_found": weights_file("face_quality").is_file(), "images": images}
    (folder / "scan.json").write_text(json.dumps(scan, indent=1, ensure_ascii=False), encoding="utf-8")
    return n


def decode_image(data):
    import cv2
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("not an image")
    return img
