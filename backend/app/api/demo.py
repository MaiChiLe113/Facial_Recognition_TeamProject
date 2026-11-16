"""Demo mode: the recorded takes and the boxes drawn over them."""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import MOCK_DIR, TRACKS_DIR
from ..services.videos import video_config, video_path

router = APIRouter(tags=["demo"])


@router.get("/api/demo/config")
def demo_config():
    cfg = video_config()
    cameras = []
    for cam in cfg["cameras"]:
        path = video_path(cam["cam_id"])
        cameras.append({**cam, "file": path.name if path else None,
                        "available": bool(path and path.exists()),
                        "url": f"/videos/{cam['cam_id']}"})
    return {"take": cfg["take"], "cameras": cameras}


@router.get("/videos/{cam_id}")
def video(cam_id: str):
    path = video_path(cam_id)
    if path is None or not path.exists():
        raise HTTPException(404, f"No video for {cam_id}. Check HAWKEYE_VIDEO_ROOT and data/video_config.json.")
    return FileResponse(path, media_type="video/webm")  # supports Range requests for seeking


@router.get("/api/tracks/{cam_id}")
def tracks(cam_id: str):
    """Real tracker output if present (data/tracks/), else the mock placeholder."""
    for folder in (TRACKS_DIR, MOCK_DIR / "tracks"):
        f = folder / f"{cam_id}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    return {"cam_id": cam_id, "source": "none", "tracks": []}
