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

# Shared Drive folder that holds AppliedML/ (student photos and cards). students.csv paths start with
# "AppliedML/". Default: two levels above HAWKEYE_VIDEO_ROOT (".../AppliedML/video data").
DRIVE_ROOT = Path(os.getenv("HAWKEYE_DRIVE_ROOT") or VIDEO_ROOT.parent.parent).expanduser()

# SQLite database file (created and seeded from data/mock/ on first start).
DB_PATH = Path(os.getenv("HAWKEYE_DB") or (DATA_DIR / "hawkeye.sqlite3")).expanduser()
