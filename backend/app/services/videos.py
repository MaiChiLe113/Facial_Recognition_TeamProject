"""Demo recordings: which file each camera plays (data/video_config.json)."""
import json

from ..config import VIDEO_CONFIG, VIDEO_ROOT


def video_config():
    return json.loads(VIDEO_CONFIG.read_text(encoding="utf-8"))


def video_path(cam_id, take=None):
    """Path of the recording this camera plays in `take` (default: the selected take), or None if the
    camera/take is unknown."""
    cfg = video_config()
    take = cfg["take"] if take is None else take
    cam = next((c for c in cfg["cameras"] if c["cam_id"] == cam_id), None)
    entry = next((t for t in cfg["takes"] if t["take"] == take), None)
    if cam is None or entry is None or cam_id not in entry["files"]:
        return None
    return VIDEO_ROOT / cam["folder"] / entry["files"][cam_id]
