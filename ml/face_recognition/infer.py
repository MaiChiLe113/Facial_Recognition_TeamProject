"""Face recognition inference.  Owner: Thuận Minh

Training and evaluation: the notebooks in this folder (triplet loss + cosine similarity was selected).
The backend and the Features demo page load this file through backend/app/core/ml_models.py
(feature name "face_recognition").

Weights file: ml/face_recognition/face_recognition.pt. The camera-calibrated ResNet-18 returns
512-d unit embeddings. The export stores input size, normalisation, and the cosine matching policy.
Set HAWKEYE_FACE_RECOGNITION_WEIGHTS to use another file, and HAWKEYE_FACE_DEVICE to "cpu" / "cuda"
(default "auto").

A face crop is an HxWx3 uint8 OpenCV array (BGR). A gallery is {student_id: [embedding, ...]};
every embedding must come from embed() of this same model.

This file is self-contained on purpose (it does not import from backend/), and it imports torch
only when a model is first needed.
"""
from __future__ import annotations

import math
import os
import threading
from pathlib import Path

import numpy as np

# Convention for every feature: ml/<feature>/<feature>.pt
_DEFAULT_WEIGHTS = Path(__file__).resolve().parent / "face_recognition.pt"
EMBEDDING_DIMENSIONS = 512

_lock = threading.Lock()
_state: dict = {}   # model, preprocessing and matching policy, filled once by _load()


def _weights_path() -> Path:
    return Path(os.environ.get("HAWKEYE_FACE_RECOGNITION_WEIGHTS", _DEFAULT_WEIGHTS))


def _load():
    """Load the model once (thread-safe)."""
    if _state:
        return _state
    with _lock:
        if _state:
            return _state
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
        from torchvision.models import resnet18

        path = _weights_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"Face recognition weights not found at {path}. Restore face_recognition.pt from Git "
                "or set HAWKEYE_FACE_RECOGNITION_WEIGHTS to an available export."
            )
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if payload.get("architecture") != "resnet18_embedding" or payload.get("embedding_dimensions") != EMBEDDING_DIMENSIONS:
            raise ValueError(f"{path} is not a resnet18_embedding / {EMBEDDING_DIMENSIONS}-d export")
        cutoff = float(payload["threshold"])
        if not -1.0 <= cutoff <= 1.0:
            raise ValueError("The weights must provide a cosine threshold between -1 and 1")
        matching = payload.get("matching", {})
        gallery_strategy = matching.get("gallery_strategy", "best_photo")
        min_score_gap = float(matching.get("min_score_gap", 0))
        if gallery_strategy not in ("best_photo", "centroid") or not 0.0 <= min_score_gap <= 2.0:
            raise ValueError("Invalid matching policy in face recognition weights")

        class FaceEmbedding(nn.Module):
            def __init__(self):
                super().__init__()
                self.backbone = resnet18(weights=None)
                self.backbone.fc = nn.Identity()

            def forward(self, images):
                return F.normalize(self.backbone(images).float(), dim=1)

        wanted = os.environ.get("HAWKEYE_FACE_DEVICE", "auto").lower()
        device = torch.device("cuda" if wanted in ("auto", "cuda") and torch.cuda.is_available() else "cpu")
        model = FaceEmbedding()
        model.load_state_dict(payload["state_dict"], strict=True)
        model.to(device).eval()
        size = payload["input_size"]
        _state.update(
            model=model,
            device=device,
            size=tuple(size) if isinstance(size, (list, tuple)) else (int(size), int(size)),
            mean=torch.tensor(payload["normalization"]["mean"], device=device).view(1, 3, 1, 1),
            std=torch.tensor(payload["normalization"]["std"], device=device).view(1, 3, 1, 1),
            threshold=cutoff,
            gallery_strategy=gallery_strategy,
            min_score_gap=min_score_gap,
        )
    return _state


def embed(face_crop):
    """One BGR uint8 face crop -> L2-normalised float32 embedding of shape (512,)."""
    import torch
    import torch.nn.functional as F

    arr = np.asarray(face_crop) if face_crop is not None else None
    if arr is None or arr.ndim != 3 or arr.shape[2] != 3 or arr.dtype != np.uint8 or 0 in arr.shape:
        raise ValueError("face_crop must be a non-empty HxWx3 uint8 (BGR) array")
    st = _load()
    rgb = np.ascontiguousarray(arr[:, :, ::-1])
    with torch.inference_mode():
        x = torch.from_numpy(rgb).to(st["device"]).permute(2, 0, 1)[None].float() / 255
        x = F.interpolate(x, size=st["size"], mode="bilinear", align_corners=False, antialias=True)
        z = st["model"](((x - st["mean"]) / st["std"]).contiguous())
    return z[0].cpu().numpy().astype(np.float32)


def _template_matrix(templates, student_id):
    mat = np.atleast_2d(np.asarray(templates, dtype=np.float64))
    if mat.size == 0:
        return None
    if mat.ndim != 2 or mat.shape[1] != EMBEDDING_DIMENSIONS or not np.isfinite(mat).all():
        raise ValueError(f"gallery embeddings for {student_id!r} must be finite {EMBEDDING_DIMENSIONS}-d vectors")
    norms = np.linalg.norm(mat, axis=1)
    if (norms == 0).any():
        raise ValueError(f"gallery embedding for {student_id!r} has zero length")
    return mat / norms[:, None]


def similarity_scores(query, gallery, *, gallery_strategy="best_photo"):
    """Score each identity using its best photo or its unit-normalized mean embedding."""
    if not isinstance(gallery, dict) or any(k is None for k in gallery):
        raise ValueError("gallery must be a {student_id: [embedding, ...]} dict")
    if gallery_strategy not in ("best_photo", "centroid"):
        raise ValueError("gallery_strategy must be best_photo or centroid")
    query = np.asarray(query, dtype=np.float64)
    scores = {}
    for student_id, templates in gallery.items():
        mat = _template_matrix(templates, student_id)
        if mat is None:
            continue
        if gallery_strategy == "centroid":
            centroid = mat.mean(axis=0)
            length = np.linalg.norm(centroid)
            if length > 1e-12:
                scores[student_id] = float(centroid @ query / length)
        else:
            scores[student_id] = float((mat @ query).max())
    return scores


def identify(face_crop, gallery, threshold):
    """Return (student_id or None, similarity).

    The weights select the gallery strategy and minimum lead over the runner-up. The best student
    wins when its score is >= threshold (None uses the threshold stored in the weights) and its
    lead exceeds the configured gap. A one-identity gallery can decide using the threshold alone.
    Unknown = (None, best score). An empty gallery gives (None, 0.0) without loading the model.
    Two different students with the exact same best score are a tie and count as Unknown.
    """
    if not isinstance(gallery, dict) or any(k is None for k in gallery):
        raise ValueError("gallery must be a {student_id: [embedding, ...]} dict")
    if threshold is not None:
        threshold = float(threshold) if not isinstance(threshold, str) else math.nan
        if not -1.0 <= threshold <= 1.0:
            raise ValueError("threshold must be a number between -1 and 1, or None")
    if not any(np.size(t) for t in gallery.values()):
        return None, 0.0
    query = embed(face_crop).astype(np.float64)
    scores = similarity_scores(query, gallery, gallery_strategy=_state.get("gallery_strategy", "best_photo"))
    if not scores:
        return None, 0.0
    if threshold is None:
        threshold = _load()["threshold"]
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    winner, best = ranked[0]
    if best < threshold or (len(ranked) > 1 and best - ranked[1][1] <= _state.get("min_score_gap", 0)):
        return None, best
    return winner, best


def threshold():
    """The cosine threshold stored in the weights file (loads the model)."""
    return _load()["threshold"]
