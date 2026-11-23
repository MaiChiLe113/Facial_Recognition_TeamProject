"""Person and face detection for the live pipeline.  Owner: Mai Chi

    detect_people(frame) -> [(x, y, w, h, score), ...]   CAM1 / CAM2 (stage "detect_people")
    detect_faces(frame)  -> [(x, y, w, h, score), ...]   attendance cam (stage "detect_faces")

Boxes are floats in pixels of the frame given (BGR array, OpenCV convention), x, y = top-left corner,
clipped to the frame. Each model is loaded once, on first use, and shared by all cameras.

Models (the same ones the recorded demo uses, so live and demo boxes agree):
  people  YOLO11n (Ultralytics), class 0 only, conf >= 0.4, as in ml/tracking/precompute_tracks.py.
          File: ml/tracking/yolo11n.pt (downloaded there by Ultralytics on first use if missing).
          Override: HAWKEYE_PERSON_DETECTOR=<path>.
  faces   OpenCV YuNet, as in ml/face_recognition/name_tracks.py.
          File: ml/face_recognition/models/face_detection_yunet_2023mar.onnx (committed, 230 KB).
          Override: HAWKEYE_FACE_DETECTOR=<path>.

Both are pre-trained detectors: they only find where a person or face is; identity, liveness and
emotion come from the group's trained models. Fine-tuning YOLO on our own frames is still open
(see ml/tracking/README.md).
"""
import os
import threading
from pathlib import Path

from ..config import REPO_DIR

PERSON_WEIGHTS = REPO_DIR / "ml" / "tracking" / "yolo11n.pt"
FACE_WEIGHTS = REPO_DIR / "ml" / "face_recognition" / "models" / "face_detection_yunet_2023mar.onnx"
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")

PERSON_CONF = 0.4        # same as precompute_tracks.py
FACE_CONF = 0.8          # same as name_tracks.py
MIN_FACE_PX = 20         # smaller faces are noise at the door; downstream models want far more pixels
FACE_MAX_SIDE = 1280     # YuNet runs on a copy no larger than this (boxes are scaled back)

_lock = threading.Lock()
_people_model = None
_face_model = None
_face_lock = threading.Lock()   # YuNet keeps its input size as state: one call at a time
_face_state = {}                # the size / threshold last set on YuNet (setting them redoes its anchors)


def _path(env, default):
    override = os.getenv(env)
    return Path(override).expanduser() if override else default


def _device():
    import torch
    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"


def _load_people():
    global _people_model
    if _people_model is None:
        with _lock:
            if _people_model is None:
                from ultralytics import YOLO       # pip install ultralytics (in requirements.txt)
                path = _path("HAWKEYE_PERSON_DETECTOR", PERSON_WEIGHTS)
                # A missing yolo11n.pt is downloaded by Ultralytics into that path.
                _people_model = (YOLO(str(path)), _device())
    return _people_model


def _load_faces():
    global _face_model
    if _face_model is None:
        with _lock:
            if _face_model is None:
                import cv2
                path = _path("HAWKEYE_FACE_DETECTOR", FACE_WEIGHTS)
                if not path.is_file():
                    raise FileNotFoundError(f"Face detector not found at {path}. Download it with:\n"
                                            f"  curl -L -o {path} {YUNET_URL}")
                _face_model = cv2.FaceDetectorYN.create(str(path), "", (320, 320), FACE_CONF)
    return _face_model


def _clip(x, y, w, h, width, height):
    x0, y0 = max(0.0, x), max(0.0, y)
    x1, y1 = min(float(width), x + w), min(float(height), y + h)
    return x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0)


def detect_people(frame, conf=PERSON_CONF):
    """Return [(x, y, w, h, score), ...] in pixels for every person in the frame (class 0 only)."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return []
    model, device = _load_people()
    result = model.predict(frame, classes=[0], conf=conf, device=device, verbose=False)[0]
    height, width = frame.shape[:2]
    people = []
    for (x0, y0, x1, y1), score in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist()):
        x, y, w, h = _clip(x0, y0, x1 - x0, y1 - y0, width, height)
        if w > 0 and h > 0:
            people.append((x, y, w, h, float(score)))
    return people


def detect_faces(frame, conf=FACE_CONF, min_size=MIN_FACE_PX):
    """Return [(x, y, w, h, score), ...] in pixels for every face in the frame, largest first."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return []
    import cv2
    model = _load_faces()
    height, width = frame.shape[:2]
    scale = min(1.0, FACE_MAX_SIDE / max(height, width))
    small = frame if scale == 1.0 else cv2.resize(frame, (round(width * scale), round(height * scale)))
    size = (small.shape[1], small.shape[0])
    with _face_lock:
        if _face_state.get("size") != size:
            model.setInputSize(size)
            _face_state["size"] = size
        if _face_state.get("conf") != conf:
            model.setScoreThreshold(conf)
            _face_state["conf"] = conf
        _, found = model.detect(small)
    faces = []
    for row in ([] if found is None else found):
        x, y, w, h = (float(v) / scale for v in row[:4])
        x, y, w, h = _clip(x, y, w, h, width, height)
        if min(w, h) >= min_size:
            faces.append((x, y, w, h, float(row[-1])))
    return sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
