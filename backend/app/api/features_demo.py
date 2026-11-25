"""Features demo page: try face recognition, anti-spoofing and emotion on webcam frames.

    GET    /api/features-demo/status                 weights found? code importable? (per feature)
    POST   /api/features-demo/infer?features=a,b&client=x[&threshold=0.4]   body = one JPEG frame -> faces, errors
                                                     and the frame's log_rows (the page collects them as the session
                                                     log). threshold: face-recognition cosine threshold in [-1, 1];
                                                     left out = the one saved in the weights (shown in /status).
                                                     liveness_threshold: minimum anti-spoofing score in [0, 1],
                                                     same rule
    POST   /api/features-demo/log                    body = {started, rows}: save a finished camera session to
                                                     logs/features_demo_<start>.csv (repo root)
    GET    /api/features-demo/gallery[?reload=true]  the registered students: the enrolment photos on the
                                                     shared Drive (same as the recorded takes on Home), embedded on first use

The body is the raw image (Content-Type image/jpeg), so no multipart library is needed.
"""
from fastapi import APIRouter, HTTPException, Request

from ..core.ml_models import DEMO_FEATURES, FEATURES
from ..services import features_demo as demo
from ..services import gallery as registered_gallery

router = APIRouter(prefix="/api/features-demo", tags=["features-demo"])


async def _image(request: Request):
    body = await request.body()
    try:
        return demo.decode(body)
    except ImportError as e:
        raise HTTPException(503, f"Missing library on the backend: {e}. Run: pip install -r requirements.txt")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/status")
def status():
    return {"features": demo.status()}


@router.post("/infer")
async def infer(request: Request, features: str = ",".join(FEATURES), client: str = "default",
                threshold: float | None = None, liveness_threshold: float | None = None):
    chosen = [f for f in features.split(",") if f]
    unknown = [f for f in chosen if f not in DEMO_FEATURES]
    if unknown:
        raise HTTPException(400, f"Unknown feature(s): {', '.join(unknown)}. Known: {', '.join(DEMO_FEATURES)}")
    if threshold is not None and not -1.0 <= threshold <= 1.0:    # also rejects nan
        raise HTTPException(400, "threshold must be a number between -1 and 1.")
    if liveness_threshold is not None and not 0.0 <= liveness_threshold <= 1.0:
        raise HTTPException(400, "liveness_threshold must be a number between 0 and 1.")
    result = demo.analyze(await _image(request), chosen, client, threshold, liveness_threshold)
    result["log_rows"] = demo.frame_log_rows(result, chosen, client)
    return result


MAX_LOG_ROWS = 200_000


@router.post("/log")
async def save_log(request: Request):
    """Save a finished camera session. Also used by navigator.sendBeacon when the tab is closed."""
    try:
        body = await request.json()
        rows, started = body["rows"], body.get("started")
        if not isinstance(rows, list):
            raise ValueError("rows must be a list")
    except Exception:  # noqa: BLE001
        raise HTTPException(400, 'Send JSON like {"started": "<ISO time>", "rows": [{...}, ...]}.')
    if len(rows) > MAX_LOG_ROWS:
        raise HTTPException(413, f"Too many rows (limit {MAX_LOG_ROWS}).")
    try:
        return {"log_file": demo.save_session_log(rows, started), "rows": len(rows)}
    except OSError as e:   # e.g. the folder is read-only
        raise HTTPException(500, f"Could not write the log: {type(e).__name__}: {e}")


@router.get("/gallery")
def gallery(reload: bool = False):
    """The registered students (their photos on the shared Drive, embedded on first use)."""
    return registered_gallery.registered(force=reload)
