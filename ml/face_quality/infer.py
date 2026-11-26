"""Face-quality inference.  Owner: Đức Mạnh

Predicts how useful a face crop is to the team's recogniser (ml/face_recognition, pinned version in the weights):
0 = useless, 1 = as good as a clean enrolment photo. Trained in 02_train_quality.ipynb on labels from
01_build_labels.ipynb; the accept threshold comes from 03_evaluate.ipynb and is stored in the weights.

Weights: ml/face_quality/face_quality.pt (override with HAWKEYE_FACE_QUALITY_WEIGHTS).
A face crop is an HxWx3 uint8 OpenCV array (BGR), cut like the recogniser's crops.

    score(face_crop)      -> float in [0, 1]
    score_batch(crops)    -> np.ndarray of floats
    threshold()           -> accept threshold (float), info() -> metadata of the weights
    build_model()         -> the torch module (used by the training notebook, so both stay identical)

Self-contained (no backend/ imports); torch is imported only when first needed.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np

_DEFAULT_WEIGHTS = Path(__file__).resolve().parent / "face_quality.pt"
INPUT_SIZE = 112
MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)

_lock = threading.Lock()
_state: dict = {}


def build_model(pretrained=False):
    """MobileNetV3-Small backbone + a small regression head with a sigmoid output (0..1)."""
    import torch.nn as nn
    from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

    net = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None)
    features = net.classifier[0].in_features
    net.classifier = nn.Sequential(nn.Linear(features, 256), nn.Hardswish(), nn.Dropout(0.2),
                                   nn.Linear(256, 1), nn.Sigmoid())
    return net


def _weights_path() -> Path:
    return Path(os.environ.get("HAWKEYE_FACE_QUALITY_WEIGHTS", _DEFAULT_WEIGHTS))


def _load():
    if _state:
        return _state
    with _lock:
        if _state:
            return _state
        import torch

        path = _weights_path()
        if not path.is_file():
            raise FileNotFoundError(f"Face quality weights not found at {path} (train them with 02_train_quality.ipynb)")
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if payload.get("architecture") != "mobilenet_v3_small_quality":
            raise ValueError(f"{path} is not a mobilenet_v3_small_quality export")
        model = build_model()
        model.load_state_dict(payload["state_dict"], strict=True)
        wanted = os.environ.get("HAWKEYE_FACE_DEVICE", "auto").lower()
        device = torch.device("cuda" if wanted in ("auto", "cuda") and torch.cuda.is_available() else "cpu")
        model.to(device).eval()
        size = int(payload.get("input_size", INPUT_SIZE))
        norm = payload.get("normalization", {"mean": MEAN, "std": STD})
        _state.update(model=model, device=device, size=size,
                      mean=torch.tensor(norm["mean"], device=device).view(1, 3, 1, 1),
                      std=torch.tensor(norm["std"], device=device).view(1, 3, 1, 1),
                      threshold=float(payload.get("threshold", 0.5)),
                      info={k: v for k, v in payload.items() if k != "state_dict"})
    return _state


def _check(crop):
    arr = np.asarray(crop) if crop is not None else None
    if arr is None or arr.ndim != 3 or arr.shape[2] != 3 or arr.dtype != np.uint8 or 0 in arr.shape:
        raise ValueError("face_crop must be a non-empty HxWx3 uint8 (BGR) array")
    return arr


def score_batch(face_crops, batch_size=128):
    """Quality of each BGR uint8 crop (any sizes), as a float array in [0, 1]."""
    import torch
    import torch.nn.functional as F

    st = _load()
    out = []
    crops = [_check(c) for c in face_crops]
    for i in range(0, len(crops), batch_size):
        xs = []
        for c in crops[i:i + batch_size]:
            x = torch.from_numpy(np.ascontiguousarray(c[:, :, ::-1])).permute(2, 0, 1)[None].float() / 255
            xs.append(F.interpolate(x, size=(st["size"], st["size"]), mode="bilinear", align_corners=False,
                                    antialias=True))
        x = torch.cat(xs).to(st["device"])
        with torch.inference_mode():
            out.append(st["model"](((x - st["mean"]) / st["std"]).contiguous()).float().cpu().numpy()[:, 0])
    return np.concatenate(out) if out else np.zeros(0, np.float32)


def score(face_crop):
    return float(score_batch([face_crop])[0])


def threshold():
    return _load()["threshold"]


def info():
    return dict(_load()["info"])
