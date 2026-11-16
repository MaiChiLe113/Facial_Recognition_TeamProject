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
