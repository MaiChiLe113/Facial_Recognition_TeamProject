"""Hand gesture detection.  Owner: Minh Thành

Finds every hand in a camera frame and names its gesture (18 HaGRID gestures, e.g. like, peace, palm, fist, one, ok, call,
plus no_gesture).

Pipeline: MediaPipe Hand Landmarker (pre-trained hand detector, hand_landmarker.task in this folder) finds the 21 points of
each hand -> they are normalised (wrist at 0, hand size 1) -> our MLP, trained on HaGRID (gesture_training.ipynb), names
the gesture.

Weights file: ml/gesture/gesture.pt (or set HAWKEYE_GESTURE_WEIGHTS), a dict saved with torch.save:
    state_dict   weights of the MLP below
    classes      gesture names in output order (HaGRID classes)

A frame is an HxWx3 uint8 OpenCV array (BGR). Self-contained; torch and mediapipe are imported lazily.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
_DEFAULT_WEIGHTS = HERE / "gesture.pt"
_LANDMARKER = HERE / "hand_landmarker.task"
HAND_CONFIDENCE = 0.7    # MediaPipe default 0.5 also finds faces as hands; 0.7 had no false hands on 600 HaGRID photos

_lock = threading.Lock()
_state: dict = {}


def _weights_path() -> Path:
    return Path(os.environ.get("HAWKEYE_GESTURE_WEIGHTS", _DEFAULT_WEIGHTS))


def _load():
    if _state:
        return _state
    with _lock:
        if _state:
            return _state
        import torch
        import torch.nn as nn
        from mediapipe.tasks.python import BaseOptions, vision

        path = _weights_path()
        if not path.is_file():
            raise FileNotFoundError(f"Gesture weights not found at {path}. Run ml/gesture/gesture_training.ipynb "
                                    "or set HAWKEYE_GESTURE_WEIGHTS.")
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        classes = list(ckpt["classes"])
        model = nn.Module()
        model.net = nn.Sequential(nn.Flatten(),
                                  nn.Linear(63, 256), nn.BatchNorm1d(256), nn.ReLU(), nn.Dropout(0.3),
                                  nn.Linear(256, 128), nn.BatchNorm1d(128), nn.ReLU(), nn.Dropout(0.3),
                                  nn.Linear(128, len(classes)))
        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        landmarker = vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(_LANDMARKER)), num_hands=2,
                                         min_hand_detection_confidence=HAND_CONFIDENCE,
                                         min_hand_presence_confidence=HAND_CONFIDENCE))
        _state.update(model=model, classes=classes, landmarker=landmarker)
    return _state


def predict(frame):
    """One BGR uint8 frame -> a list with one {"label", "score", "box": [x, y, w, h] in pixels} per hand (empty if none)."""
    import mediapipe as mp
    import torch

    arr = np.asarray(frame) if frame is not None else None
    if arr is None or arr.ndim != 3 or arr.shape[2] != 3 or arr.dtype != np.uint8 or 0 in arr.shape:
        raise ValueError("frame must be a non-empty HxWx3 uint8 (BGR) array")
    st = _load()
    h, w = arr.shape[:2]
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(arr[:, :, ::-1]))
    with _lock:
        hands = st["landmarker"].detect(image).hand_landmarks
    results = []
    for hand in hands:
        p = np.array([[pt.x * w, pt.y * h, pt.z * w] for pt in hand], dtype=np.float32)
        q = p - p[:1]
        q = q / np.linalg.norm(q[:, :2], axis=1).max()
        with torch.inference_mode():
            probs = torch.softmax(st["model"].net(torch.from_numpy(q)[None]), dim=1)[0].numpy()
        best = int(probs.argmax())
        results.append({"label": st["classes"][best], "score": float(probs[best]),
                        "box": [float(p[:, 0].min()), float(p[:, 1].min()), float(np.ptp(p[:, 0])), float(np.ptp(p[:, 1]))]})
    return results
