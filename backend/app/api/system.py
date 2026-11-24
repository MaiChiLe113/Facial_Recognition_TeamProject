from fastapi import APIRouter

from ..config import VIDEO_ROOT

router = APIRouter(tags=["system"])


@router.get("/")
def root():
    return {"app": "Hawkeye API", "ui": "Open the web app at http://localhost:5173 (run `npm run dev` in frontend/)",
            "try": ["/api/health", "/api/dashboard", "/api/demo/config", "/docs"]}


@router.get("/api/health")
def health():
    return {"ok": True, "video_root": str(VIDEO_ROOT), "video_root_exists": VIDEO_ROOT.exists()}


@router.get("/api/system/models")
def system_models():
    """System log page: every model file the app infers with (version label, modified time, fingerprint) and the
    change history from logs/model_changes.jsonl (see app/services/model_log.py)."""
    from ..services import model_log
    models = model_log.check()
    return {"models": models, "history": list(reversed(model_log.history())),
            "versions_file": "ml/model_versions.json", "log_file": "logs/model_changes.jsonl"}
