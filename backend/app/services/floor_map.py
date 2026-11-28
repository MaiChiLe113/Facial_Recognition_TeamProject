"""Person boxes on cam_1 / cam_2 -> positions on the 2D Room 204 map (the live tracking map and its door events).

Feet = bottom-centre of the box, projected with the camera's floor homography (data/calibration/, made by ml/aruco)
to map fractions (x 0 left -> 1 right, y 0 top -> 1 bottom, room204_map.json convention).
"""
import json
from functools import lru_cache

import numpy as np

from ..config import REPO_DIR

CALIBRATION = REPO_DIR / "data" / "calibration"
MAP_CAMS = ("cam_1", "cam_2")       # cameras that see feet and have a homography
FRAME_W, FRAME_H = 1280, 720        # frame size the homographies were estimated on
FEET_CUT = 0.995          # box bottom at or below this fraction of the frame = feet not visible
DOOR_MARGIN_X = 0.08      # map units either side of the wall that still count as "at the door"
DOOR_MARGIN_Y = 0.08      # extra map units above/below the door opening (homography is only estimated)

# Where each camera's floor homography can be trusted (map x range). cam_1 stands in the corridor and also
# sees into the room through the glass, but people seen through the glass are not on its floor plane;
# cam_2 stands in the room and also "sees" a poster in the corridor. Points outside are dropped, not clipped.
VALID_X = {"cam_1": (-0.02, 0.36), "cam_2": (0.25, 1.02)}
VALID_Y = (-0.02, 1.05)


@lru_cache(maxsize=None)
def room_map():
    return json.loads((CALIBRATION / "room204_map.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def homography(cam_id, live=False):
    """3x3 image-pixel -> map-fraction homography of cam_1 / cam_2.
    live=True: the current camera pose (<cam>_homography_live.json, falls back to the recorded one);
    otherwise the pose of the recorded takes (<cam>_homography.json)."""
    path = CALIBRATION / f"{cam_id}_homography_live.json"
    if not (live and path.is_file()):
        path = CALIBRATION / f"{cam_id}_homography.json"
    return np.array(json.loads(path.read_text(encoding="utf-8"))["H"], dtype=float)


def to_map(cam_id, box, live=False):
    """Map position (x, y) of a normalised box [x, y, w, h], or None when the feet are not visible or the
    point falls outside the part of the map this camera's homography is valid for.
    live=True uses the calibration of the current camera pose (the recorded takes were filmed at another one)."""
    if cam_id not in MAP_CAMS:
        return None
    x, y, w, h = (float(v) for v in box[:4])
    if y + h >= FEET_CUT:
        return None
    p = homography(cam_id, live) @ np.array([(x + w / 2) * FRAME_W, (y + h) * FRAME_H, 1.0])
    if abs(p[2]) < 1e-12:
        return None
    mx, my = float(p[0] / p[2]), float(p[1] / p[2])
    lo, hi = VALID_X[cam_id]
    if not (lo <= mx <= hi and VALID_Y[0] <= my <= VALID_Y[1]):
        return None
    return mx, my


def zone_of(x, y):
    """corridor / door / room for a map position."""
    m = room_map()
    wall, (d0, d1) = m["corridor_wall_x"], m["door"]["y"]
    if abs(x - wall) <= DOOR_MARGIN_X and d0 - DOOR_MARGIN_Y <= y <= d1 + DOOR_MARGIN_Y:
        return "door"
    return "corridor" if x < wall else "room"
