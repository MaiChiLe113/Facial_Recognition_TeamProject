"""Emotion recognition inference.  Owner: Minh Thành

Training code: this folder (FER2013 or RAF-DB, 7 classes, ResNet-18 fine-tuned; see README.md).
The backend and the Features demo page load this file through backend/app/core/ml_models.py
(feature name "emotion").

Weights file: ml/emotion/emotion.pt (git-ignored), or set HAWKEYE_EMOTION_WEIGHTS.
The checkpoint is a dict saved with torch.save:
    state_dict   weights of torchvision resnet18 whose fc is Linear(512, len(classes))
    classes      list of label names in output order (default: CLASSES below)
    img_size     int, square input size (default 224)
    mean, std    per-channel normalisation, RGB, 0..1 scale (default ImageNet)
    gray         optional bool: the model was trained on grayscale faces (replicated to 3 channels)

A face crop is an HxWx3 uint8 OpenCV array (BGR). Self-contained; torch is imported lazily.
"""
from __future__ import annotations

import os
import threading
from collections import deque
from pathlib import Path

import numpy as np

CLASSES = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]

# Convention for every feature: ml/<feature>/<feature>.pt
_DEFAULT_WEIGHTS = Path(__file__).resolve().parent / "emotion.pt"

_lock = threading.Lock()
_state: dict = {}
_recent: deque = deque(maxlen=5)   # last probability vectors, averaged to steady the label


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
                f"Emotion weights not found at {path}. Train the model (ml/emotion/) and save the "
                "checkpoint there as emotion.pt, or set HAWKEYE_EMOTION_WEIGHTS."
            )
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        classes = list(ckpt.get("classes", CLASSES))
        model = resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, len(classes))
        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        _state.update(
            model=model,
            classes=classes,
            size=int(ckpt.get("img_size", 224)),
            gray=bool(ckpt.get("gray", False)),
            mean=torch.tensor(ckpt.get("mean", [0.485, 0.456, 0.406])).view(1, 3, 1, 1),
            std=torch.tensor(ckpt.get("std", [0.229, 0.224, 0.225])).view(1, 3, 1, 1),
        )
    return _state


def predict(face_crop, smooth=True):
    """One BGR uint8 face crop -> {"label": str, "score": float, "scores": {label: prob}}.

    With smooth=True the probabilities are averaged with the last few calls, so call reset()
    when the face changes or disappears.
    """
    import torch
    import torch.nn.functional as F
    from PIL import Image

    arr = np.asarray(face_crop) if face_crop is not None else None
    if arr is None or arr.ndim != 3 or arr.shape[2] != 3 or arr.dtype != np.uint8 or 0 in arr.shape:
        raise ValueError("face_crop must be a non-empty HxWx3 uint8 (BGR) array")
    st = _load()
    img = Image.fromarray(np.ascontiguousarray(arr[:, :, ::-1]))
    if st["gray"]:
        img = img.convert("L").convert("RGB")
    img = img.resize((st["size"], st["size"]), Image.BILINEAR)
    x = torch.from_numpy(np.asarray(img, dtype=np.float32) / 255.0).permute(2, 0, 1)[None]
    with torch.inference_mode():
        probs = F.softmax(st["model"]((x - st["mean"]) / st["std"]), dim=1)[0].numpy()
    if smooth:
        _recent.append(probs)
        probs = np.mean(_recent, axis=0)
    best = int(probs.argmax())
    return {"label": st["classes"][best], "score": float(probs[best]),
            "scores": {c: float(p) for c, p in zip(st["classes"], probs)}}


def reset():
    """Forget the smoothing history (a different face, or no face)."""
    _recent.clear()
