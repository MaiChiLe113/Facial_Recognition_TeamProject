"""Features demo page: try face recognition, anti-spoofing and emotion on webcam frames.

    GET    /api/features-demo/status                 weights found? code importable? (per feature)
    POST   /api/features-demo/infer?features=a,b&client=x   body = one JPEG frame -> faces, errors and the frame's
                                                     log_rows (the page collects them as the session log)
    POST   /api/features-demo/log                    body = {started, rows}: save a finished camera session to
                                                     logs/features_demo_<start>.csv (repo root)
    GET    /api/features-demo/gallery[?reload=true]  the registered students: the enrolment photos on the
                                                     shared Drive (same as MultiCam), embedded on first use

The body is the raw image (Content-Type image/jpeg), so no multipart library is needed.
"""
from fastapi import APIRouter, HTTPException, Request

from ..core.ml_models import FEATURES
from ..services import features_demo as demo

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
async def infer(request: Request, features: str = ",".join(FEATURES), client: str = "default"):
    chosen = [f for f in features.split(",") if f]
    unknown = [f for f in chosen if f not in FEATURES]
    if unknown:
        raise HTTPException(400, f"Unknown feature(s): {', '.join(unknown)}. Known: {', '.join(FEATURES)}")
    result = demo.analyze(await _image(request), chosen, client)
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
    return demo.registered(force=reload)
