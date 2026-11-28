"""Backs the Features demo page: run selected models on one webcam frame.

    face_recognition  who is it (against the registered students, app/services/gallery.py)
    anti_spoofing     live or spoof (printed photo / phone screen)
    emotion           the facial expression
    glasses_detection whether each face is wearing glasses
    mask_detection    whether each face is wearing a face mask (rule-based, needs YuNet landmarks)
    gesture           the hand gesture of every hand in the frame: result["hands"]

The models come from ml/<feature>/infer.py + <feature>.pt (see app/core/ml_models.py). A feature
whose weights or libraries are missing is reported in "errors" and the others still run.
Faces are found and cut exactly as in the doorway pipeline: app/pipeline/detector.detect_faces (YuNet) and
ml_models.crop_face with each model's margin (ml_models.MARGIN). The registered faces are app/services/gallery.py.
"""
import csv
import threading
import time
from datetime import datetime
from collections import deque

from ..config import REPO_DIR
from ..core.ml_models import DEMO_FEATURES, crop_face, load_infer, weights_status
from . import gallery

LIVENESS_FRAMES = 10
MIN_FACE_PX = 36     # webcam faces smaller than this are too far away for the models (as before: 60 px * 0.6)

_lock = threading.Lock()
LOG_DIR = REPO_DIR / "logs"          # root/logs/, git-ignored
LOG_COLUMNS = ["time", "client", "features", "face", "name", "student_id", "similarity", "threshold", "live", "liveness_score", "liveness_threshold",
               "emotion", "emotion_score", "box_x", "box_y", "box_w", "box_h", "frame_ms", "errors"]
_log_lock = threading.Lock()
_live_buffers = {}   # client id -> deque of recent crops of the main face


def _find_faces(image):
    """[(x, y, w, h), ...] in pixels, largest first: the pipeline's face detector."""
    from ..pipeline.detector import detect_faces
    return [tuple(f[:4]) for f in detect_faces(image, min_size=MIN_FACE_PX)]


def decode(jpeg_bytes):
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The body is not a decodable image (send a JPEG or PNG).")
    return image


def _default_threshold(feature):
    """The threshold saved inside the weights file (loads the model on first use)."""
    infer = load_infer(feature)
    if feature == "face_recognition":
        return float(infer.threshold())
    return float(infer._load()["threshold"])    # anti_spoofing has no public accessor; ml/ is not ours to edit


def _live_confidence(is_live, score, threshold):
    """How sure the Live / Spoof label is, 0.5..1: 0.5 right at the threshold, 1.0 at the far end of that side.
    (The raw score is P(live); this is the confidence of the label that is shown, so one number reads the same
    for both labels. It is a distance to the decision boundary, not a calibrated probability.)"""
    span = (1.0 - threshold) if is_live else threshold
    frac = (abs(score - threshold) / span) if span > 0 else 1.0
    return round(0.5 + 0.5 * min(1.0, frac), 4)


def status():
    """Per feature: are the weights where the app looks for them, and is the code importable."""
    out = []
    for feature in DEMO_FEATURES:
        info = weights_status(feature)
        try:
            load_infer(feature)
            info["code"] = True
        except Exception as e:  # noqa: BLE001
            info["code"] = False
            info["error"] = f"{type(e).__name__}: {e}"
        info["registered_faces"] = len(gallery.registered_faces()[0]) if feature == "face_recognition" else None
        info["threshold"] = None
        if feature in ("face_recognition", "anti_spoofing") and info["code"] and info["found"]:
            try:
                info["threshold"] = _default_threshold(feature)     # the value saved in the weights
            except Exception as e:  # noqa: BLE001
                info["error"] = f"{type(e).__name__}: {e}"
        out.append(info)
    return out


def analyze(image, features, client="default", threshold=None, liveness_threshold=None):
    """Run the selected features on one BGR frame. Returns {"faces": [...], "errors": {...}, "ms": ...}.
    threshold: cosine threshold for face recognition; liveness_threshold: minimum live score (0..1) for
    anti-spoofing. None = the one saved in the weights."""
    start = time.perf_counter()
    height, width = image.shape[:2]
    boxes = _find_faces(image)
    faces = [{"box": [x / width, y / height, w / width, h / height]} for x, y, w, h in boxes]
    errors = {}

    def run(feature, fn):
        try:
            fn(load_infer(feature))
        except Exception as e:  # noqa: BLE001 - a missing model must not stop the others
            if isinstance(e, FileNotFoundError) and not weights_status(feature)["found"]:
                errors[feature] = "Missing model weights"
            else:
                errors[feature] = f"{type(e).__name__}: {e}"

    if "anti_spoofing" in features:
        def live(infer):
            with _lock:
                buffer = _live_buffers.setdefault(client, deque(maxlen=LIVENESS_FRAMES))
                if not boxes:
                    buffer.clear()
                    return
                buffer.append(crop_face(image, boxes[0], "anti_spoofing"))
                crops = list(buffer)
            # the largest face is smoothed over the last frames; every other face (e.g. a face shown on a phone
            # screen, usually smaller than the person holding it) is checked on this frame alone
            for i, face in enumerate(faces):
                result = infer.check(crops if i == 0 else [crop_face(image, boxes[i], "anti_spoofing")])
                score = result.get("score")
                if liveness_threshold is None or score is None:
                    is_live = bool(result["live"])
                else:                             # custom threshold; a 0.0 score means "no usable crop": never live
                    is_live = score > 0.0 and score >= liveness_threshold
                confidence = None
                if score is not None:
                    limit = liveness_threshold if liveness_threshold is not None else _default_threshold("anti_spoofing")
                    confidence = _live_confidence(is_live, score, limit)
                face.update(live=is_live, liveness_score=score, liveness_confidence=confidence)
        run("anti_spoofing", live)

    if "glasses_detection" in features and boxes:
        def detect_glasses(infer):
            for face, box in zip(faces, boxes):
                crop = crop_face(image, box, "glasses_detection")
                if crop is not None:
                    face.update(infer.predict(crop))
        run("glasses_detection", detect_glasses)

    if "mask_detection" in features and boxes:
        def detect_mask(infer):
            from ..pipeline.detector import detect_faces_landmarks
            marked = detect_faces_landmarks(image, min_size=MIN_FACE_PX)   # same detector, now with the 5 landmarks
            for face, (x, y, w, h) in zip(faces, boxes):
                cx, cy = x + w / 2, y + h / 2
                near = min(marked, key=lambda f: (f[0] + f[2] / 2 - cx) ** 2 + (f[1] + f[3] / 2 - cy) ** 2, default=None)
                if near is None or abs(near[0] + near[2] / 2 - cx) > w / 2 or abs(near[1] + near[3] / 2 - cy) > h / 2:
                    continue
                r = infer.check(image, near[5])
                if r["mask"] is not None:
                    face.update(mask=bool(r["mask"]), mask_score=r["score"])
        run("mask_detection", detect_mask)

    if "face_recognition" in features and boxes:
        def recognise(infer):
            gallery.load_registered()
            if gallery.is_loading():         # first load still running: do not block the frame
                for face in faces:
                    face.update(student_id=None, name=None, similarity=0.0, registered=False, loading=True)
                return
            profiles, names = gallery.registered_profiles()
            for face, box in zip(faces, boxes):
                if face.get("live") is False:    # never identify a spoof (same rule as the live pipeline)
                    face.update(student_id=None, name=None, similarity=0.0, registered=bool(profiles[0]),
                                recognition_skipped="spoof")
                    continue
                crop = crop_face(image, box, "face_recognition")
                student_id, similarity, cutoff = gallery.identify_face(infer, crop, profiles, threshold, face.get("glasses"))
                face.update(student_id=student_id, name=names.get(student_id) if student_id else None,
                            similarity=similarity, registered=bool(profiles[0]), recognition_threshold=cutoff)
        run("face_recognition", recognise)

    if "emotion" in features:
        def feel(infer):
            if not boxes:
                infer.reset()
                return
            for face, box in zip(faces, boxes):
                if face.get("live") is False:    # a spoof has no emotion
                    continue
                result = infer.predict(crop_face(image, box, "emotion"))
                face.update(emotion=result["label"], emotion_score=result.get("score"))
        run("emotion", feel)

    hands = []
    if "gesture" in features:
        def gesture(infer):                  # whole frame, not face crops; boxes as fractions like the faces
            for hand in infer.predict(image):
                x, y, w, h = hand["box"]
                hands.append({"label": hand["label"], "score": hand["score"], "box": [x / width, y / height, w / width, h / height]})
        run("gesture", gesture)

    result = {"faces": faces, "errors": errors, "ms": round((time.perf_counter() - start) * 1000, 1)}
    if "gesture" in features:
        result["hands"] = hands
    if "face_recognition" in features:
        try:                                 # the value actually used: the custom one, else the weights' own
            result["threshold"] = threshold if threshold is not None else float(load_infer("face_recognition").threshold())
        except Exception:  # noqa: BLE001 - the model error is already in errors
            result["threshold"] = threshold
    if "anti_spoofing" in features:
        try:
            result["liveness_threshold"] = (liveness_threshold if liveness_threshold is not None
                                            else _default_threshold("anti_spoofing"))
        except Exception:  # noqa: BLE001 - the model error is already in errors
            result["liveness_threshold"] = liveness_threshold
    return result



def _warm_up():
    """Load every model whose weights file exists (so the first webcam frame is not slow), then the registered faces."""
    for feature in DEMO_FEATURES:
        try:
            if weights_status(feature)["found"]:
                load_infer(feature)._load()
        except Exception:  # noqa: BLE001 - reported later by /api/features-demo/status or in the frame result
            pass
    gallery.registered()


def start_preload():
    """Warm up the models and load the registered faces in a background thread (called when the backend starts)."""
    threading.Thread(target=_warm_up, daemon=True, name="features-demo-warmup").start()


def frame_log_rows(result, features, client):
    """The log rows of one analysed frame: one per face, or one blank row (face = 0) when there is none.
    The page keeps these for the whole camera session and shows them; see save_session_log()."""
    def cell(v, digits=None):
        return "" if v is None else (round(v, digits) if digits is not None and isinstance(v, float) else v)

    base = {"time": datetime.now().isoformat(timespec="milliseconds"), "client": client, "features": "+".join(features),
            "frame_ms": result.get("ms"), "errors": "; ".join(f"{k}: {v}" for k, v in result.get("errors", {}).items())}
    rows = []
    for i, f in enumerate(result.get("faces", []), 1):
        x, y, w, h = f["box"]
        cutoff = f.get("recognition_threshold")
        if cutoff is None:
            cutoff = result.get("threshold")
        rows.append({**base, "face": i, "name": cell(f.get("name")), "student_id": cell(f.get("student_id")),
                     "similarity": cell(f.get("similarity"), 4),
                     "threshold": cell(cutoff, 4) if "similarity" in f else "", "live": cell(f.get("live")),
                     "liveness_score": cell(f.get("liveness_score"), 4),
                     "liveness_threshold": cell(result.get("liveness_threshold"), 4) if "live" in f else "", "emotion": cell(f.get("emotion")),
                     "emotion_score": cell(f.get("emotion_score"), 4),
                     "box_x": round(x, 4), "box_y": round(y, 4), "box_w": round(w, 4), "box_h": round(h, 4)})
    return rows or [{**base, "face": 0}]


def save_session_log(rows, started=None):
    """Write one camera session (camera on -> off) to logs/features_demo_<start>.csv. Returns the path
    relative to the repo ("logs/features_demo_2026-11-23_004512.csv"), or None when there is nothing to save."""
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return None
    try:
        start = datetime.fromisoformat(str(started).replace("Z", "+00:00")).astimezone() if started else datetime.now()
    except ValueError:
        start = datetime.now()
    with _log_lock:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"features_demo_{start:%Y-%m-%d_%H%M%S}.csv"
        n = 2
        while path.exists():                       # two sessions that started in the same second
            path = LOG_DIR / f"features_demo_{start:%Y-%m-%d_%H%M%S}_{n}.csv"
            n += 1
        with path.open("w", newline="", encoding="utf-8-sig") as fh:   # BOM: Excel reads Vietnamese names
            writer = csv.DictWriter(fh, fieldnames=LOG_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    return f"logs/{path.name}"
