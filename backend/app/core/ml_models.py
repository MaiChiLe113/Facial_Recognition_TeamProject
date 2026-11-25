"""Finds the inference code and weights of the camera features in the repo's ml/ folder.

Convention: ml/<feature>/infer.py is the code and ml/<feature>/<feature>.pt is the weights file.

    FEATURES = face_recognition, anti_spoofing, emotion

    infer = load_infer("anti_spoofing")      # the module ml/anti_spoofing/infer.py (imports no torch yet)
    weights_file("anti_spoofing")            # <repo>/ml/anti_spoofing/anti_spoofing.pt
    weights_status("anti_spoofing")          # {"feature", "weights", "found", "expected_file"}
    crop_face(image, box, "anti_spoofing")   # the face cut out the way that model expects (MARGIN)

Each infer.py also accepts HAWKEYE_<FEATURE>_WEIGHTS (e.g. HAWKEYE_ANTI_SPOOFING_WEIGHTS) as an override.
"""
import importlib.util
import os
from pathlib import Path

from ..config import REPO_DIR

ML_DIR = REPO_DIR / "ml"
FEATURES = ("face_recognition", "anti_spoofing", "emotion")
DEMO_FEATURES = (*FEATURES, "glasses_detection", "gesture")

# Margin around a detected face box, per model, as a fraction of the box size on each side.
# anti_spoofing was trained on crops with 25 % (ml/anti_spoofing/try_liveness.py); emotion scores the same on the raw box.
MARGIN = {"face_recognition": 0.1, "anti_spoofing": 0.25, "emotion": 0.0, "glasses_detection": 0.1}

_modules = {}


def crop_face(image, box, feature):
    """The face at box (x, y, w, h[, ...] in pixels) cut from a BGR image with that feature's MARGIN, clipped
    to the image. None when the image is missing or the crop is empty. Used by the Features demo and the pipeline."""
    _check(feature)
    if not hasattr(image, "shape"):
        return None
    height, width = image.shape[:2]
    x, y, w, h = (float(v) for v in box[:4])
    m = MARGIN[feature]
    x0, y0 = int(max(0, x - w * m)), int(max(0, y - h * m))
    x1, y1 = int(min(width, x + w * (1 + m))), int(min(height, y + h * (1 + m)))
    return image[y0:y1, x0:x1] if x1 > x0 and y1 > y0 else None


def _check(feature):
    if feature not in DEMO_FEATURES:
        raise KeyError(f"Unknown feature '{feature}'. Known: {', '.join(DEMO_FEATURES)}")


def weights_file(feature):
    """Where the app looks for the weights: ml/<feature>/<feature>.pt (or HAWKEYE_<FEATURE>_WEIGHTS)."""
    _check(feature)
    override = os.getenv(f"HAWKEYE_{feature.upper()}_WEIGHTS")
    return Path(override).expanduser() if override else ML_DIR / feature / f"{feature}.pt"


def weights_status(feature):
    path = weights_file(feature)
    return {"feature": feature, "weights": str(path), "found": path.is_file(),
            "expected_file": f"ml/{feature}/{feature}.pt"}


def load_infer(feature):
    """Import ml/<feature>/infer.py once and return the module."""
    _check(feature)
    if feature not in _modules:
        path = ML_DIR / feature / "infer.py"
        if not path.is_file():
            raise FileNotFoundError(f"{path} does not exist")
        spec = importlib.util.spec_from_file_location(f"hawkeye_ml_{feature}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _modules[feature] = module
    return _modules[feature]
