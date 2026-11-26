"""Shared paths and readers for presence verification + door audit.  Owner: Đức Mạnh

Read-only access to the team's data: data/tracks/ (Mai Chi), data/calibration/, data/ground_truth/.
Nothing in this package writes outside ml/presence_verification/.
"""
import csv
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = REPO / "data"
OUTPUTS = HERE / "outputs"                          # git-ignored
MODEL_FILE = HERE / "presence_verification.joblib"  # git-ignored, made by train.py

MAP_CAMS = ("cam_1", "cam_2")       # cameras that see feet and have a homography
FRAME_W, FRAME_H = 1280, 720        # frame size the homographies were estimated on


@lru_cache(maxsize=None)
def room_map():
    return json.loads((DATA / "calibration" / "room204_map.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def homography(cam_id, live=False):
    """3x3 image-pixel -> map-fraction homography of cam_1 / cam_2.
    live=True: the current camera pose (<cam>_homography_live.json, falls back to the recorded one);
    otherwise the pose of the recorded takes (<cam>_homography.json)."""
    path = DATA / "calibration" / f"{cam_id}_homography_live.json"
    if not (live and path.is_file()):
        path = DATA / "calibration" / f"{cam_id}_homography.json"
    return np.array(json.loads(path.read_text(encoding="utf-8"))["H"], dtype=float)


def metres_per_unit():
    """(metres per map unit in x, in y) from room204_map.json "scale_per_m" (map units per metre)."""
    s = room_map()["scale_per_m"]
    return 1.0 / s["x"], 1.0 / s["y"]


def takes():
    """Take numbers that have track files."""
    root = DATA / "tracks"
    return sorted(int(p.name[4:]) for p in root.glob("take*") if p.is_dir() and p.name[4:].isdigit())


def load_tracks(take, cam_id):
    path = DATA / "tracks" / f"take{take}" / f"{cam_id}.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("tracks", [])


def load_ground_truth(take):
    """Rows of data/ground_truth/take<N>.csv as dicts (times as float), or [] when there is none."""
    path = DATA / "ground_truth" / f"take{take}.csv"
    if not path.is_file():
        return []
    rows = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r["appear_s"], r["disappear_s"] = float(r["appear_s"]), float(r["disappear_s"])
            rows.append(r)
    return rows


def check_ins_from_tracks(take):
    """Check-in events of a recorded take: one per named attendance_cam track, at its name_from time
    (when name_tracks.py named it) or its first keyframe. Returns [{t, student_id, similarity, source_track}]."""
    events = []
    for tr in load_tracks(take, "attendance_cam"):
        if not tr.get("name") or not tr.get("keyframes"):
            continue
        t = tr.get("name_from", tr["keyframes"][0]["t"])
        events.append({"t": float(t), "student_id": tr["name"], "similarity": tr.get("similarity"),
                       "source_track": tr["global_id"]})
    return sorted(events, key=lambda e: e["t"])


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path
