"""Hawkeye API.

Run: uvicorn app.main:app --reload --port 8000   (from the backend/ folder)
"""
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import MOCK_DIR, TRACKS_DIR, VIDEO_CONFIG, VIDEO_ROOT
from .mock_store import build_dashboard

app = FastAPI(title="Hawkeye")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _video_config():
    return json.loads(VIDEO_CONFIG.read_text(encoding="utf-8"))


def _video_path(cam_id):
    cfg = _video_config()
    cam = next((c for c in cfg["cameras"] if c["cam_id"] == cam_id), None)
    take = next((t for t in cfg["takes"] if t["take"] == cfg["take"]), None)
    if cam is None or take is None:
        return None
    return VIDEO_ROOT / cam["folder"] / take["files"][cam_id]


@app.get("/")
def root():
    return {"app": "Hawkeye API", "ui": "Open the web app at http://localhost:5173 (run `npm run dev` in frontend/)",
            "try": ["/api/health", "/api/dashboard", "/api/demo/config", "/docs"]}


@app.get("/api/health")
def health():
    return {"ok": True, "video_root": str(VIDEO_ROOT), "video_root_exists": VIDEO_ROOT.exists()}


@app.get("/api/dashboard")
def dashboard():
    # TODO (Đức Mạnh): read from the database instead of mock files.
    return build_dashboard()


@app.get("/api/demo/config")
def demo_config():
    cfg = _video_config()
    cameras = []
    for cam in cfg["cameras"]:
        path = _video_path(cam["cam_id"])
        cameras.append({**cam, "file": path.name if path else None,
                        "available": bool(path and path.exists()),
                        "url": f"/videos/{cam['cam_id']}"})
    return {"take": cfg["take"], "cameras": cameras}


@app.get("/videos/{cam_id}")
def video(cam_id: str):
    path = _video_path(cam_id)
    if path is None or not path.exists():
        raise HTTPException(404, f"No video for {cam_id}. Check HAWKEYE_VIDEO_ROOT and data/video_config.json.")
    return FileResponse(path, media_type="video/webm")  # supports Range requests for seeking


@app.get("/api/tracks/{cam_id}")
def tracks(cam_id: str):
    """Real tracker output if present (data/tracks/), else the mock placeholder."""
    for folder in (TRACKS_DIR, MOCK_DIR / "tracks"):
        f = folder / f"{cam_id}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    return {"cam_id": cam_id, "source": "none", "tracks": []}


# TODO (Đức Mạnh): live mode
# - WebSocket /ws/camera/{cam_id}: receive frames from the browser camera pages
# - WebSocket /ws/dashboard: push boxes, events and map positions to the UI
# - POST /api/students: registration from the "+ Add person" page
