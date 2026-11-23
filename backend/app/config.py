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

# Shared Drive folder that holds AppliedML/ (the team's enrolment photos and cards). The students' photo_folder /
# student_card paths start with "AppliedML/". Default: two levels above HAWKEYE_VIDEO_ROOT (".../AppliedML/video data").
DRIVE_ROOT = Path(os.getenv("HAWKEYE_DRIVE_ROOT") or VIDEO_ROOT.parent.parent).expanduser()

# Photos uploaded on the Add person page (POST /api/students): data/photos/<student_id_vn>/, git-ignored.
PHOTOS_REL = "data/photos"
PHOTOS_DIR = REPO_DIR / PHOTOS_REL

# Face photo types accepted anywhere (enrolment folders, uploads); browsers can show all but HEIC/HEIF.
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
BROWSER_IMAGE_EXT = IMAGE_EXT - {".heic", ".heif"}


def is_upload(rel):
    """True for a photo_folder / student_card path inside the repo ("data/...", Add person uploads)."""
    return bool(rel) and Path(rel).parts[:1] == ("data",)


def student_file(rel, drive_root=None):
    """A student's photo_folder or student_card path: an upload is inside the repo, anything else ("AppliedML/...")
    is on the shared Drive."""
    return REPO_DIR / rel if is_upload(rel) else (drive_root or DRIVE_ROOT) / rel

# SQLite database file (created and seeded from data/mock/ on first start).
DB_PATH = Path(os.getenv("HAWKEYE_DB") or (DATA_DIR / "hawkeye.sqlite3")).expanduser()
