"""Demo recordings: which file each camera plays (data/video_config.json)."""
import json

from ..config import VIDEO_CONFIG, VIDEO_ROOT


def video_config():
    return json.loads(VIDEO_CONFIG.read_text(encoding="utf-8"))


def video_path(cam_id):
    """Path of the recording this camera plays in the selected take, or None if the camera/take is unknown."""
    cfg = video_config()
    cam = next((c for c in cfg["cameras"] if c["cam_id"] == cam_id), None)
    take = next((t for t in cfg["takes"] if t["take"] == cfg["take"]), None)
    if cam is None or take is None:
        return None
    return VIDEO_ROOT / cam["folder"] / take["files"][cam_id]
