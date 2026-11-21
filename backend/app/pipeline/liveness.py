"""Anti-spoofing (liveness).  Owner: Hồng Minh

Training code: ml/anti_spoofing/. Must be our own trained / fine-tuned model.

Model: MobileNetV2 (ImageNet backbone, partly fine-tuned) with a 1-logit head,
trained by ml/anti_spoofing/train.py. sigmoid(logit) = P(live).

Weights file: <repo>/weights/liveness_mobilenetv2.pt (git-ignored; copy it from Drive/Kaggle),
or set HAWKEYE_LIVENESS_WEIGHTS to another path. The decision threshold is stored inside the
checkpoint (chosen on the dev split), so it is not hard-coded here.

This file is self-contained on purpose (it does not import from ml/) so the backend can
run without the training folder on its path.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np

# backend/app/pipeline/liveness.py -> parents[3] is the repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_WEIGHTS = _REPO_ROOT / "weights" / "liveness_mobilenetv2.pt"

MAX_FRAMES = 10  # average the score over at most the last 10 crops

_lock = threading.Lock()
_state: dict = {}  # filled once by _load(): model, threshold, size, mean, std


def _weights_path() -> Path:
    return Path(os.environ.get("HAWKEYE_LIVENESS_WEIGHTS", _DEFAULT_WEIGHTS))


def _load():
    """Load the model once (thread-safe)."""
    if _state:
        return _state
    with _lock:
        if _state:
            return _state
        import torch
        import torch.nn as nn
        from torchvision.models import mobilenet_v2

        path = _weights_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"Liveness weights not found at {path}. Train with ml/anti_spoofing/train.py "
                "and copy the .pt file there, or set HAWKEYE_LIVENESS_WEIGHTS."
            )
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        model = mobilenet_v2(weights=None)
        model.classifier = nn.Sequential(nn.Dropout(0.2), nn.Linear(model.classifier[1].in_features, 1))
        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        _state.update(
            model=model,
            threshold=float(ckpt["threshold"]),
            size=int(ckpt.get("img_size", 224)),
            mean=torch.tensor(ckpt["mean"]).view(3, 1, 1),
            std=torch.tensor(ckpt["std"]).view(3, 1, 1),
        )
    return _state


def _preprocess(crop, st):
    """One face crop -> normalised CHW tensor.

    `crop` is an HxWx3 uint8 array in OpenCV order (BGR), or a PIL image (RGB).
    Resizing uses PIL bilinear, the same as training, to avoid a train/serve mismatch.
    """
    import torch
    from PIL import Image

    if isinstance(crop, Image.Image):
        img = crop.convert("RGB")
    else:
        arr = np.asarray(crop)
        if arr.ndim == 2:
            arr = np.stack([arr] * 3, axis=-1)
        img = Image.fromarray(np.ascontiguousarray(arr[..., :3][..., ::-1]).astype(np.uint8))  # BGR -> RGB
    img = img.resize((st["size"], st["size"]), Image.BILINEAR)
    x = torch.from_numpy(np.asarray(img, dtype=np.float32) / 255.0).permute(2, 0, 1)
    return (x - st["mean"]) / st["std"]


def _is_usable(crop) -> bool:
    if crop is None:
        return False
    size = getattr(crop, "size", None)  # numpy: element count, PIL: (w, h)
    return bool(size) if not isinstance(size, tuple) else all(size)


def check(face_crops):
    """Given ~10 recent crops of one face, return {"live": bool, "score": float}.

    score = mean P(live) over the crops (0..1, higher = more likely a real face).
    live  = score >= the threshold saved with the model.
    No usable crops -> {"live": False, "score": 0.0} (never accept without evidence).
    """
    import torch

    crops = [c for c in (face_crops or []) if _is_usable(c)][-MAX_FRAMES:]
    if not crops:
        return {"live": False, "score": 0.0}

    st = _load()
    batch = torch.stack([_preprocess(c, st) for c in crops])
    with torch.inference_mode():
        probs = torch.sigmoid(st["model"](batch).squeeze(1))
    score = float(probs.mean())
    return {"live": score >= st["threshold"], "score": score}
