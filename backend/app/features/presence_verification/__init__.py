"""Presence verification + door audit (Đức Mạnh's innovative feature).

The model lives in ml/presence_verification/ (infer.py + presence_verification.joblib, made by its train.py).
This plug-in only serves it:

    GET /api/features/presence_verification/take/{take}   door audit + presence scores of a recorded take,
                                                          with map trails for the Room 204 map
    GET /api/features/presence_verification/model         what was trained and how it was chosen
    GET /api/features/presence_verification/live          check-ins received from the pipeline so far

Switched on in backend/pipeline.json ("features": {"presence_verification": true}). Without the model file
setup() fails, the feature shows "failed" in GET /api/pipeline/status with the reason, and its routes are
not mounted; nothing else is affected.
TODO (live mode): run audit_door / score_session on the live events once the pipeline emits map positions.
"""
import importlib.util
import threading

from fastapi import APIRouter, HTTPException

from ...config import REPO_DIR
from ...core.features import Feature
from ...core.registry import register_feature

INFER_FILE = REPO_DIR / "ml" / "presence_verification" / "infer.py"

router = APIRouter()
_current = None
_cache, _cache_lock = {}, threading.Lock()


def load_module():
    spec = importlib.util.spec_from_file_location("hawkeye_ml_presence_verification", INFER_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@register_feature("presence_verification")
class PresenceVerification(Feature):
    router = router

    def setup(self, bus):
        global _current
        if not INFER_FILE.is_file():
            raise FileNotFoundError(f"{INFER_FILE} does not exist")
        self.infer = load_module()
        self.model = self.infer.model_info()        # raises FileNotFoundError when the model is not trained
        self.check_ins = []
        bus.subscribe("check_in", self.on_check_in, owner=self.name)
        _current = self

    def on_check_in(self, ev):
        self.check_ins.append({"t": ev.t, "student_id": ev.student_id, "global_id": ev.global_id})

    def info(self):
        return {"model": self.model, "live_check_ins": len(self.check_ins)}


def _feature():
    if _current is None:
        raise HTTPException(503, "presence_verification is not running")
    return _current


@router.get("/take/{take}")
def take_result(take: int):
    f = _feature()
    with _cache_lock:
        if take not in _cache:
            try:
                _cache[take] = f.infer.analyze_take(take)
            except FileNotFoundError as e:
                raise HTTPException(404, f"No data for take {take}: {e}")
        return _cache[take]


@router.get("/model")
def model():
    return _feature().model


@router.get("/live")
def live():
    return {"check_ins": _feature().check_ins}
