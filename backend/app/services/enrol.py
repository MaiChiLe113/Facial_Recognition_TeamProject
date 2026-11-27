"""live_face_scan: the AI face scan for the Add person page (Đức Mạnh's innovative feature). Replaces the manual photo upload.

A scan session collects the best face stills for 3 head poses (SLOTS), PER_SLOT each. Every frame, from the live
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
    "front": ((-12, 12), (-10, 10)),      # yaw > 0 = nose towards the image right = head turned to the person's left
    "left": ((12, 55), (-20, 20)),        # pitch < 0 = chin up
    "right": ((-55, -12), (-20, 20)),     # ranges touch: no dead zone between front and the sides
}
# Chin up / chin down slots were dropped (2026-11-27): the landmark pitch barely registered chin up and the quality
# model scored those stills low, which made the scan slow and frustrating for little recognition gain.
# The landmark pose is rough and its zero differs per face (pitch most), so each session first measures the person's
# own "looking straight" pose and reports yaw / pitch relative to it.
CALIB_FRAMES = 4            # frontal-looking frames averaged (median) for the baseline
CALIB_MAX = (25, 30)        # |raw yaw|, |raw pitch| a frame may have to count as "looking straight"
PER_SLOT = 3
# Live scan: the slots are filled in SLOTS order (straight, left, right). Only the current target
# slot accepts stills, so a passing "right" view no longer jumps ahead while the hint asks for "left".
# The target's ranges are widened by TARGET_MARGIN degrees, and
# preview poses are smoothed over POSE_SMOOTH frames so slot and hint stop flickering from landmark jitter.
TARGET_MARGIN = 3.0
POSE_SMOOTH = 3
MIN_FACE_PX = 110           # face box height in the full-resolution still (phone / 1080p)
MIN_FACE_PX_LOW = 80        # for a 720p (or smaller) camera
BRIGHTNESS = (60, 200)      # mean grey level of the face crop
DETECT_W = 640              # face detection width (the live preview size)
SECOND_FACE_RATIO = 0.5    # another face this big (vs the largest) refuses the frame
MIN_POSE_GAP = 4.0          # degrees: stills of one slot must differ this much in yaw or pitch (else the better one stays)
LIVENESS_WINDOW = 10        # crops averaged for liveness
MASK_WINDOW = 3             # mask scores (ml/mask_detection) averaged, so one odd frame does not flip the hint
GLASSES_WINDOW = 3          # same for glasses (ml/glasses_detection): the scan asks to take them off
# The checkpoint's threshold (EER on LCC-FASD dev) is 0.024: nearly every webcam frame, a printed photo or a phone
# screen included, scores above it. Like QUALITY_THRESHOLD_WEBCAM, the scan uses its own bar on the mean P(live).
# None = the checkpoint's value. Set from logs/enrol_frames.jsonl "live_score" (real scan vs photo attack).
LIVENESS_THRESHOLD_WEBCAM = None
SESSION_TTL = 30 * 60
FRAME_LOG = None            # logs/enrol_frames.jsonl when None: quality / pose / reason of every scored frame
FAIL_LOG = None             # logs/enrol_failures.jsonl in the repo when None (tests point it elsewhere)
VIDEO_FPS = 5.0
VIDEO_MAX_S = 60
VIDEO_MAX_BYTES = 300 * 2**20
# The weights carry 0.78, chosen on Kaggle 64 px crops (03_evaluate.ipynb). Real webcam frames score lower
# (median 0.67-0.75 on the team's AppliedML photos), so the scan uses a threshold calibrated on those photos.
QUALITY_THRESHOLD_WEBCAM = 0.65
# The score level also moves between sessions (same light and face size: straight median 0.70 in one scan, 0.55 in
# the next), so the bar is relative to this person's own straight frames in this session: QUALITY_REF_N straight
# preview scores give a reference, and a frame passes at reference - QUALITY_REL_MARGIN (never above the model's
# threshold, never below QUALITY_FLOOR). A blurred frame still falls below the person's own level.
QUALITY_REF_N = 8
QUALITY_REL_MARGIN = 0.06
QUALITY_FLOOR = 0.45
DUPLICATE_MIN_VOTES = 2     # kept stills that must match the same registered student to warn about a duplicate
# Every new still must look like the person already kept in this session (someone else stepping in front of the
# camera between two photos is refused): best cosine similarity to a kept still, face_recognition embeddings.
# Below the recogniser's own threshold (0.53) on purpose: the same face turned left vs straight scores lower.
SAME_PERSON_MIN = 0.35

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
        # v2+ (04_finetune_team.ipynb) chose its threshold on webcam / phone crops: use it; v1's 0.78 was Kaggle-only
        thr = q.threshold() if q.info().get("threshold_domain") == "webcam" else QUALITY_THRESHOLD_WEBCAM
        return q.score, thr, "face_quality"
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


def slot_for(yaw, pitch, target=None):
    """The slot (yaw, pitch) fits. target: tried first with its ranges widened (live scan's current slot)."""
    if target is not None:
        (y0, y1), (p0, p1) = SLOTS[target]
        if y0 - TARGET_MARGIN <= yaw <= y1 + TARGET_MARGIN and p0 - TARGET_MARGIN <= pitch <= p1 + TARGET_MARGIN:
            return target
    for name, ((y0, y1), (p0, p1)) in SLOTS.items():
        if y0 <= yaw <= y1 and p0 <= pitch <= p1:
            return name
    return None


def _vary_hint(target, have):
    """In the slot with `have` stills already kept: ask for a slightly different angle of the SAME pose, since a slot's
    stills must differ by MIN_POSE_GAP degrees."""
    n = f"photo {have + 1} of {PER_SLOT}"
    if target == "front":
        return f"straight, {n}: keep facing the camera, move your head slightly (a little up, down or sideways)"
    return f"{target} side, {n}: stay turned, move slightly (turn a bit more or less, or tilt a little up / down)"


def _hint(missing, yaw, pitch, have=0):
    """Tell the person how to reach the first missing slot (their own left / right). Each hint names that slot, and
    overshooting it says "a little less", so "turn back" is never mistaken for "now do the other side".
    have: stills already kept for that slot; once one is kept, "hold still" becomes "move slightly" (_vary_hint)."""
    if not missing:
        return "done"
    target = missing[0]
    (y0, y1), (p0, p1) = SLOTS[target]
    still = _vary_hint(target, have) if have else "hold still"
    if target == "front":
        return "look straight at the camera" if not (y0 <= yaw <= y1 and p0 <= pitch <= p1) else still
    if not p0 <= pitch <= p1:
        return f"{target} side: keep your chin level"
    far = yaw > y1 if target == "left" else yaw < y0          # past the slot, away from the camera
    if far:
        return f"{target} side: a little less, turn back slightly"
    if y0 <= yaw <= y1:
        return still
    return f"{target} side: turn your head to your {target}" + (" a bit more" if (yaw > 5 if target == "left" else yaw < -5) else "")


# ---- sessions ---------------------------------------------------------------------------------------------

def new_session(source="live"):
    _expire()
    _warm_gallery()
    sid = uuid.uuid4().hex[:16]
    with _lock:
        _sessions[sid] = {"id": sid, "source": source, "created": time.time(), "slots": {k: [] for k in SLOTS},
                          "crops": [], "liveness": None, "duplicate": None, "frames": 0, "failed": None,
                          "calib": [], "baseline": None, "poses": [], "dup_votes": {}, "q_front": [], "mask": [], "glasses": []}
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


def remove_still(s, slot, index):
    """Drop one kept still (the x on its thumbnail); the slot becomes missing again and the scan can refill it."""
    with _lock:
        entries = s["slots"].get(slot)
        if entries is None or not 0 <= index < len(entries):
            raise IndexError(index)
        del entries[index]


def missing_slots(s):
    return [k for k in SLOTS if len(s["slots"][k]) < PER_SLOT]


def summary(s):
    _, thr, model = quality_model()
    return {"session_id": s["id"], "source": s["source"], "model": model, "threshold": round(thr, 4),
            "per_slot": PER_SLOT, "missing": missing_slots(s), "done": not missing_slots(s),
            "liveness": s["liveness"], "duplicate": s["duplicate"], "frames": s["frames"], "failed": s.get("failed"),
            "baseline": s.get("baseline"),
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
    return {k: v for k, v in e.items() if k not in ("jpeg", "crop", "emb")}


# ---- analysis ---------------------------------------------------------------------------------------------

def analyse(s, image, final=False, t=None):
    """Analyse one BGR frame for session s. final=True: keep it in its slot if it passes. t = video time (s)."""
    import cv2
    from ..core.ml_models import crop_face
    from ..pipeline.detector import detect_faces_landmarks

    h, w = image.shape[:2]
    s["frames"] += 1
    out = {"faces": 0, "accepted": False, "kept": False, "frame_size": [w, h], "t": t}
    # YuNet runs on a copy at most DETECT_W wide, like the live preview, so a full-resolution still finds the same face
    # (on large frames with a big face it sometimes found none); boxes and landmarks are scaled back
    k = min(1.0, DETECT_W / w)
    small = image if k == 1.0 else cv2.resize(image, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)
    faces = [(fx / k, fy / k, fw / k, fh / k, fc, [(px / k, py / k) for px, py in fm])
             for fx, fy, fw, fh, fc, fm in detect_faces_landmarks(small, min_size=max(12, round(24 * k)))]
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
    raw_yaw, raw_pitch = head_pose(marks)
    if s["baseline"] is None:
        if CALIB_FRAMES <= 0:
            s["baseline"] = (0.0, 0.0)
        elif abs(raw_yaw) <= CALIB_MAX[0] and abs(raw_pitch) <= CALIB_MAX[1]:
            s["calib"].append((raw_yaw, raw_pitch))
            if len(s["calib"]) >= CALIB_FRAMES:
                s["baseline"] = tuple(round(float(np.median([c[i] for c in s["calib"]])), 1) for i in (0, 1))
    if s["baseline"] is None:
        return {**out, "yaw": raw_yaw, "pitch": raw_pitch, "reason": "calibrating",
                "hint": f"look straight at the camera ({len(s['calib'])}/{CALIB_FRAMES})", "missing": missing,
                "done": not missing, "duplicate": s["duplicate"]}
    yaw, pitch = round(raw_yaw - s["baseline"][0], 1), round(raw_pitch - s["baseline"][1], 1)
    ordered = s["source"] == "live"
    if ordered and not final and POSE_SMOOTH > 1:      # median of the last preview poses: steadier slot and hint
        s["poses"] = (s.get("poses", []) + [(yaw, pitch)])[-POSE_SMOOTH:]
        yaw, pitch = (round(float(np.median([p[i] for p in s["poses"]])), 1) for i in (0, 1))
    crop = crop_face(image, (x, y, bw, bh), "face_quality")
    grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    bright = float(grey.mean())
    scorer, thr, model = quality_model()
    # the trained model sees an eye-aligned crop framed like its Kaggle training images (much looser than the box)
    q = float(scorer(_infer("face_quality").align_crop(image, marks))) if scorer else heuristic(crop, bh, yaw, pitch)
    target = missing[0] if ordered and missing else None
    slot = slot_for(yaw, pitch, target)
    if slot == "front" and not final and len(s.setdefault("q_front", [])) < QUALITY_REF_N:
        s["q_front"].append(q)

    # Live scan: liveness comes from the preview frames only. Re-checking it on the full-resolution still mixed crop
    # sizes in the window and often flipped it to "not live". A video has no preview, so every sampled frame counts.
    live_still = final and s["source"] == "live" and s["crops"]
    if not live_still:
        s["crops"] = (s["crops"] + [crop_face(image, (x, y, bw, bh), "anti_spoofing")])[-LIVENESS_WINDOW:]
    if not live_still and (final or len(s["crops"]) % 3 == 0):   # every 3rd preview frame, every video frame
        try:
            res = _infer("anti_spoofing").check(s["crops"])
            if LIVENESS_THRESHOLD_WEBCAM is not None:
                res["live"] = res["score"] >= LIVENESS_THRESHOLD_WEBCAM
            s["liveness"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()}
        except Exception as e:  # noqa: BLE001 - missing weights must not stop the scan; reported instead
            s["liveness"] = {"live": None, "score": None, "error": str(e)}
    masked, mask_score = _mask(s, image, marks)
    wears_glasses, glasses_score = _glasses(s, crop_face(image, (x, y, bw, bh), "glasses_detection"))
    out.update(box=[round(x / w, 4), round(y / h, 4), round(bw / w, 4), round(bh / h, 4)],
               landmarks=[[round(px / w, 4), round(py / h, 4)] for px, py in marks],
               yaw=yaw, pitch=pitch, slot=slot, quality=round(q, 4), model=model, threshold=round(_quality_bar(s, thr, slot), 4),
               brightness=round(bright, 1), face_px=round(bh), face_conf=round(float(conf), 4), liveness=s["liveness"],
               mask_score=mask_score, glasses_score=glasses_score)

    # full-resolution stills from a 720p camera are smaller: same flow, lower size floor
    min_px = MIN_FACE_PX if max(w, h) >= 1280 and min(w, h) > 720 else MIN_FACE_PX_LOW
    if (s["liveness"] or {}).get("live") is False:
        reason, hint = "not_live", "use a real face (photos and screens are refused)"
    elif masked:
        reason, hint = "mask", "please take off your face mask to continue the scan"
    elif wears_glasses:
        reason, hint = "glasses", "please take off your glasses to continue the scan"
    elif bright < BRIGHTNESS[0]:
        reason, hint = "too_dark", "too dark: move to a brighter place"
    elif bright > BRIGHTNESS[1]:
        reason, hint = "too_bright", "too bright or back-lit: face the light"
    elif bh < min_px:
        reason, hint = "too_small", "move closer"
    elif slot is None:
        reason, hint = "between_poses", _hint(missing, yaw, pitch)
    elif target is not None and slot != target and slot in missing:   # a later pose, not reached yet
        reason, hint = "other_pose", _hint(missing, yaw, pitch)
    elif q < _quality_bar(s, thr, slot):
        reason, hint = "low_quality", "hold still (image not sharp enough)"
    elif slot in missing and not _would_keep(s, slot, q, yaw, pitch):
        reason, hint = "same_view", _vary_hint(slot, len(s["slots"][slot]))
    else:
        reason = "ok"
        hint = "hold still" if slot in missing else _hint(missing, yaw, pitch)
    out.update(reason=reason, hint=hint, accepted=reason == "ok")

    if final and out["accepted"]:
        rec_crop = crop_face(image, (x, y, bw, bh), "face_recognition")
        emb, same = _same_person(s, rec_crop)
        out["same_person"] = same
        if same is not None and same < SAME_PERSON_MIN:
            out.update(reason="other_person", accepted=False,
                       hint="a different person was detected: only the person being registered, or start again")
    if final and out["accepted"]:
        out["kept"] = _keep(s, slot, image, crop, out, glasses_of(crop), emb)
        if out["kept"]:
            _vote_duplicate(s, rec_crop)
        missing = missing_slots(s)
        out["hint"] = "done" if not missing else _hint(missing, yaw, pitch, len(s["slots"][missing[0]]))
    out.update(missing=missing_slots(s), done=not missing_slots(s), duplicate=s["duplicate"])
    _log_frame(s, out, target, final)
    return out


def _log_frame(s, out, target, final):
    """Append one line per scored frame, to measure the quality score per pose (threshold tuning)."""
    entry = {"session_id": s["id"], "source": s["source"], "final": final, "target": target,
             **{k: out.get(k) for k in ("slot", "yaw", "pitch", "quality", "threshold", "reason", "face_px",
                                        "face_conf", "brightness", "kept", "mask_score",
                                        "glasses_score", "same_person")},
             "live_score": (out.get("liveness") or {}).get("score")}
    log = FRAME_LOG or _repo_dir() / "logs" / "enrol_frames.jsonl"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # logging must not break the scan


def _mask(s, image, marks):
    """(masked, score): the mean of the last MASK_WINDOW mask scores; (False, None) if the check cannot decide."""
    try:
        score = _infer("mask_detection").check(image, marks)["score"]
    except Exception:  # noqa: BLE001 - the mask check must not stop the scan
        score = None
    if score is None:
        return False, None
    s["mask"] = (s.setdefault("mask", []) + [score])[-MASK_WINDOW:]
    mean = float(np.mean(s["mask"]))
    return mean >= _infer("mask_detection").THRESHOLD, round(mean, 4)


def _glasses(s, crop):
    """(wears_glasses, score): mean of the last GLASSES_WINDOW glasses scores against the model's threshold;
    (False, None) when the model is missing or fails (the scan goes on)."""
    try:
        m = _infer("glasses_detection")
        score = float(m.predict(crop)["glasses_score"])
        thr = float(m._load()["threshold"])
    except Exception:  # noqa: BLE001
        return False, None
    s["glasses"] = (s.setdefault("glasses", []) + [score])[-GLASSES_WINDOW:]
    mean = float(np.mean(s["glasses"]))
    return mean >= thr, round(mean, 4)


def _quality_bar(s, thr, slot):
    """The quality a frame of this slot needs in this session (see QUALITY_REF_N)."""
    bar = thr
    ref = s.get("q_front") or []
    if len(ref) >= QUALITY_REF_N:
        bar = max(QUALITY_FLOOR, min(thr, float(np.median(ref)) - QUALITY_REL_MARGIN))
    return bar


def glasses_of(crop):
    try:
        r = _infer("glasses_detection").predict(crop)
        return {"glasses": bool(r["glasses"]), "score": round(float(r["glasses_score"]), 4)}
    except Exception:  # noqa: BLE001
        return None


def _warm_gallery():
    """Start loading the registered faces in the background (they are empty until a page first loads them)."""
    try:
        from . import gallery
        if not gallery.registered_faces()[0]:
            threading.Thread(target=gallery.load_registered, daemon=True, name="enrol-gallery").start()
    except Exception:  # noqa: BLE001
        pass


def _vote_duplicate(s, crop):
    """Check every kept still, not only the first: one view can match the wrong person (a straight still matched
    another student while the side views matched the right one). Warn once DUPLICATE_MIN_VOTES stills agree."""
    d = duplicate_of(crop)
    if not d:
        if s["duplicate"] is None and d is False and not s["dup_votes"]:
            s["duplicate"] = False
        return
    v = s["dup_votes"].setdefault(d["student_id"], {**d, "votes": 0})
    v["votes"] += 1
    v["score"] = max(v["score"], d["score"])
    best = max(s["dup_votes"].values(), key=lambda e: (e["votes"], e["score"]))
    if best["votes"] >= DUPLICATE_MIN_VOTES:
        s["duplicate"] = dict(best)


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


def _near(entries, yaw, pitch):
    return [e for e in entries if abs(e["yaw"] - yaw) < MIN_POSE_GAP and abs(e["pitch"] - pitch) < MIN_POSE_GAP]


def _would_keep(s, slot, q, yaw, pitch):
    """False when a still like this would not be kept: nearly the same view as a better kept still, or the slot is
    full of better ones."""
    entries = s["slots"][slot]
    near = _near(entries, yaw, pitch)
    if near:
        return q > max(e["quality"] for e in near)
    return len(entries) < PER_SLOT or q > min(e["quality"] for e in entries)


def _same_person(s, crop):
    """(embedding, best cosine similarity to the session's kept stills). similarity is None for the first still or
    when the recogniser is unavailable (the check is skipped, the scan goes on)."""
    try:
        emb = np.asarray(_infer("face_recognition").embed(crop), dtype=np.float32)
    except Exception:  # noqa: BLE001
        return None, None
    kept = [e["emb"] for v in s["slots"].values() for e in v if e.get("emb") is not None]
    if not kept:
        return emb, None
    return emb, round(float(max(np.dot(k, emb) for k in kept)), 4)


def _keep(s, slot, image, crop, info, glasses, emb=None):
    import cv2
    entries = s["slots"][slot]
    near = _near(entries, info["yaw"], info["pitch"])
    if not _would_keep(s, slot, info["quality"], info["yaw"], info["pitch"]):
        return False
    ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    entry = {"slot": slot, "quality": info["quality"], "yaw": info["yaw"], "pitch": info["pitch"],
             "face_px": info["face_px"], "brightness": info["brightness"], "frame_size": info["frame_size"],
             "liveness": (s["liveness"] or {}).get("score"), "glasses": glasses,
             "t": info.get("t"), "jpeg": jpeg.tobytes(), "emb": emb}
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
