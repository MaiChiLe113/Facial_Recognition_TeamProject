"""Resolve demo video paths for the tracking scripts.  Owner: Mai Chi

Same rules as backend/app/services/videos.py:
    HAWKEYE_VIDEO_ROOT (from backend/.env) / cameras[].folder / takes[].files[cam_id]

Usage:
    from paths import video_path
    video_path("cam_1")          # configured take from data/video_config.json
    video_path("cam_2", take=7)  # a specific take

Run this file to print the resolved path of every camera:
    ml/.venv/bin/python ml/tracking/paths.py [--take N]
"""
import json
import os
from pathlib import Path

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[2]
ENV_FILE = REPO / "backend" / ".env"
VIDEO_CONFIG = REPO / "data" / "video_config.json"


def video_root():
    """HAWKEYE_VIDEO_ROOT from backend/.env (the process environment wins), else data/videos/."""
    root = os.getenv("HAWKEYE_VIDEO_ROOT") or dotenv_values(ENV_FILE).get("HAWKEYE_VIDEO_ROOT")
    return Path(root or (REPO / "data" / "videos")).expanduser()


def video_config():
    return json.loads(VIDEO_CONFIG.read_text(encoding="utf-8"))


def camera_ids():
    return [c["cam_id"] for c in video_config()["cameras"]]


def configured_take():
    return video_config()["take"]


CONVERTED_DIR = REPO / "data" / "raw" / "converted"


def converted_path(cam_id, take=None):
    """Where the constant-30-fps MP4 of this recording lives (see notebooks/01_explore.ipynb)."""
    take = configured_take() if take is None else int(take)
    return CONVERTED_DIR / f"{cam_id}_take{take}.mp4"


def video_path(cam_id, take=None, prefer_converted=True):
    """Path of the recording for cam_id in `take` (default: the configured take).

    Returns data/raw/converted/<cam_id>_take<N>.mp4 when it exists and prefer_converted is True:
    the browser .webm originals report 1000 fps and no duration, so tracking uses the MP4.
    Raises ValueError for an unknown camera or take. Does not check that the original exists.
    """
    cfg = video_config()
    cam = next((c for c in cfg["cameras"] if c["cam_id"] == cam_id), None)
    if cam is None:
        raise ValueError(f"Unknown camera {cam_id!r}. Known: {[c['cam_id'] for c in cfg['cameras']]}")
    take = cfg["take"] if take is None else int(take)
    entry = next((t for t in cfg["takes"] if t["take"] == take), None)
    if entry is None:
        raise ValueError(f"Unknown take {take!r}. Known: {[t['take'] for t in cfg['takes']]}")
    filename = entry["files"].get(cam_id)
    if not filename:
        raise ValueError(f"Take {take} has no file for camera {cam_id!r} in {VIDEO_CONFIG}")
    if prefer_converted and converted_path(cam_id, take).exists():
        return converted_path(cam_id, take)
    return video_root() / cam["folder"] / filename


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Print the resolved demo video path per camera.")
    p.add_argument("--take", type=int, default=None)
    a = p.parse_args()
    take = configured_take() if a.take is None else a.take
    print(f"Video root: {video_root()} (exists: {video_root().exists()})")
    print(f"Take: {take}" + (" (configured)" if a.take is None else ""))
    for cam_id in camera_ids():
        for label, path in (("original", video_path(cam_id, take, prefer_converted=False)),
                            ("converted", converted_path(cam_id, take))):
            size = f", {path.stat().st_size / 1e6:.1f} MB" if path.exists() else ""
            print(f"  {cam_id:15s} {label:9s} exists={path.exists()}{size}  {path}")
        print(f"  {cam_id:15s} -> uses {video_path(cam_id, take).name}")
