from fastapi import APIRouter, Request

router = APIRouter(tags=["pipeline"])


@router.get("/api/pipeline/status")
def pipeline_status(request: Request):
    """State of every stage per camera, every event subscriber and every feature."""
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        return {"running": False, "error": getattr(request.app.state, "engine_error", "Engine not started")}
    return engine.status()
