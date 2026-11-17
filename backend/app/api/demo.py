"""Demo mode: the recorded takes and the boxes drawn over them.

Every route takes an optional ?take=N; without it the take selected in data/video_config.json is used.
"""
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import MOCK_DIR, TRACKS_DIR
from ..services.videos import video_config, video_path

router = APIRouter(tags=["demo"])


@router.get("/api/demo/config")
def demo_config(take: Optional[int] = None):
    cfg = video_config()
    take = cfg["take"] if take is None else take
    cameras = []
    for cam in cfg["cameras"]:
        path = video_path(cam["cam_id"], take)
        cameras.append({**cam, "file": path.name if path else None,
                        "available": bool(path and path.exists()),
                        "url": f"/videos/{cam['cam_id']}?take={take}"})
    return {"take": take, "default_take": cfg["take"], "cameras": cameras}


@router.get("/videos/{cam_id}")
def video(cam_id: str, take: Optional[int] = None):
    path = video_path(cam_id, take)
    if path is None or not path.exists():
        raise HTTPException(404, f"No video for {cam_id}. Check HAWKEYE_VIDEO_ROOT and data/video_config.json.")
    return FileResponse(path, media_type="video/webm")  # supports Range requests for seeking


@router.get("/api/tracks/{cam_id}")
def tracks(cam_id: str, take: Optional[int] = None):
    """Real tracker output for the take (data/tracks/take<N>/), else the mock placeholder for the selected take."""
    default = video_config()["take"]
    take = default if take is None else take
    folders = [TRACKS_DIR / f"take{take}"]
    if take == default:
        folders += [TRACKS_DIR, MOCK_DIR / "tracks"]   # older single-take layout, then the mock boxes
    for folder in folders:
        f = folder / f"{cam_id}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    return {"cam_id": cam_id, "source": "none", "tracks": []}
