"""Finds the inference code and weights of each basic feature in the repo's ml/ folder.

Convention: ml/<feature>/infer.py is the code and ml/<feature>/<feature>.pt is the weights file.

    FEATURES = face_recognition, anti_spoofing, emotion

    infer = load_infer("anti_spoofing")      # the module ml/anti_spoofing/infer.py (imports no torch yet)
    weights_file("anti_spoofing")            # <repo>/ml/anti_spoofing/anti_spoofing.pt
    weights_status("anti_spoofing")          # {"feature", "weights", "found", "expected_file"}

Each infer.py also accepts HAWKEYE_<FEATURE>_WEIGHTS (e.g. HAWKEYE_ANTI_SPOOFING_WEIGHTS) as an override.
"""
import importlib.util
import os
from pathlib import Path

from ..config import REPO_DIR

ML_DIR = REPO_DIR / "ml"
FEATURES = ("face_recognition", "anti_spoofing", "emotion")

_modules = {}


def _check(feature):
    if feature not in FEATURES:
        raise KeyError(f"Unknown feature '{feature}'. Known: {', '.join(FEATURES)}")


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
