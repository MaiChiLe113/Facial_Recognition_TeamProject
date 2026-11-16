"""Paths and settings. Override with environment variables or backend/.env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = REPO_DIR / "data"
MOCK_DIR = DATA_DIR / "mock"
TRACKS_DIR = DATA_DIR / "tracks"          # real tracker output goes here
VIDEO_CONFIG = DATA_DIR / "video_config.json"

# Folder with cam_1/, cam_2/, attendance_cam/. Falls back to data/videos/.
VIDEO_ROOT = Path(os.getenv("HAWKEYE_VIDEO_ROOT") or (DATA_DIR / "videos")).expanduser()
