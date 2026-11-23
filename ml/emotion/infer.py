"""Emotion recognition inference.  Owner: Minh Thành

Model: ResNet-18 from ImageNet, conv1 + layer1 frozen, the rest fine-tuned on FER2013 + AffectNet (7 classes).
Training and results: emotion_training.ipynb in this folder. Test accuracy: FER2013 0.707, AffectNet 0.661.
The backend and the Features demo page load this file through backend/app/core/ml_models.py
(feature name "emotion").

Weights file: ml/emotion/emotion.pt (committed on main), or set HAWKEYE_EMOTION_WEIGHTS.
The checkpoint is a dict saved with torch.save:
    state_dict   weights of torchvision resnet18 whose fc is Linear(512, len(classes))
    classes      list of label names in output order
    face_size    the face is made grayscale and resized to this square first (48, as in FER2013)
    img_size     then enlarged to this square before the network (96)
    mean, std    ImageNet normalisation (the gray face is copied to 3 channels)

A face crop is an HxWx3 uint8 OpenCV array (BGR). Self-contained; torch is imported lazily.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np

CLASSES = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]

# Convention for every feature: ml/<feature>/<feature>.pt
_DEFAULT_WEIGHTS = Path(__file__).resolve().parent / "emotion.pt"

_lock = threading.Lock()
_state: dict = {}
_recent: deque = deque(maxlen=100)   # (time, probabilities) of recent calls, averaged to steady the label
SMOOTH_SECONDS = 1.0                 # average over the last second, whatever the frame rate


def _weights_path() -> Path:
    return Path(os.environ.get("HAWKEYE_EMOTION_WEIGHTS", _DEFAULT_WEIGHTS))


def _load():
    if _state:
        return _state
    with _lock:
        if _state:
            return _state
        import torch
        import torch.nn as nn
        from torchvision.models import resnet18

        path = _weights_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"Emotion weights not found at {path}. Train the model (ml/emotion/emotion_training.ipynb) "
                "and save the checkpoint there as emotion.pt, or set HAWKEYE_EMOTION_WEIGHTS."
            )
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        classes = list(ckpt["classes"])
        model = resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, len(classes))
        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        _state.update(
            model=model,
            classes=classes,
            face_size=int(ckpt["face_size"]),
            size=int(ckpt["img_size"]),
            mean=torch.tensor(ckpt["mean"]).view(1, 3, 1, 1),
            std=torch.tensor(ckpt["std"]).view(1, 3, 1, 1),
        )
    return _state


def predict(face_crop, smooth=True):
    """One BGR uint8 face crop -> {"label": str, "score": float, "scores": {label: prob}}.

    With smooth=True the probabilities are averaged with the calls of the last second, so call reset()
    when the face changes or disappears.
    """
    import cv2
    import torch
    import torch.nn.functional as F

    arr = np.asarray(face_crop) if face_crop is not None else None
    if arr is None or arr.ndim != 3 or arr.shape[2] != 3 or arr.dtype != np.uint8 or 0 in arr.shape:
        raise ValueError("face_crop must be a non-empty HxWx3 uint8 (BGR) array")
    st = _load()
    gray = cv2.resize(cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY), (st["face_size"], st["face_size"]))
    x = torch.from_numpy(gray.astype(np.float32) / 255.0)[None, None]
    x = F.interpolate(x, size=st["size"], mode="bilinear").repeat(1, 3, 1, 1)
    with torch.inference_mode():
        probs = F.softmax(st["model"]((x - st["mean"]) / st["std"]), dim=1)[0].numpy()
    if smooth:
        now = time.monotonic()
        _recent.append((now, probs))
        probs = np.mean([p for t, p in _recent if now - t <= SMOOTH_SECONDS], axis=0)
    best = int(probs.argmax())
    return {"label": st["classes"][best], "score": float(probs[best]),
            "scores": {c: float(p) for c, p in zip(st["classes"], probs)}}


def reset():
    """Forget the smoothing history (a different face, or no face)."""
    _recent.clear()
