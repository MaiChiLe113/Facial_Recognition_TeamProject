"""Approximate floor -> Room 204 map calibration without floor markers.  Owner: Mai Chi

Each camera is treated as a pinhole camera with no roll, centred principal point and an assumed
70 degree horizontal field of view. Camera height and horizon row are fitted from the track boxes
of standing people (assumed 1.7 m tall): feet_row = horizon + (camera_height / 1.7) * box_height_px.
The classroom door (seen by cam_1 and cam_2) then fixes where each camera sits on the map.
The result is turned into four image/map point pairs, so the rest of the pipeline uses a normal
cv2 homography. Everything here is an estimate: replace with measured floor markers when possible.
"""
import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
FRAME_W, FRAME_H = 1280, 720
PERSON_H = 1.7          # m, assumed height of a standing person
HFOV_DEG = 70.0         # assumed horizontal field of view of the phone/webcam cameras
F = (FRAME_W / 2) / np.tan(np.radians(HFOV_DEG / 2))

MAP = json.loads((REPO / "data" / "calibration" / "room204_map.json").read_text(encoding="utf-8"))
SX, SY = MAP["scale_per_m"]["x"], MAP["scale_per_m"]["y"]      # map units per metre
WALL_X_M = MAP["corridor_wall_x"] / SX
DOOR_C_M = np.array([WALL_X_M, MAP["door"]["centre"][1] / SY])

# Pixel position of the floor at the two door jambs (picked by eye on data/calibration/<cam>_frame.png).
DOOR_JAMBS = {"cam_1": [(722, 582), (872, 547)],   # left (north) jamb, right (south) jamb
              "cam_2": [(432, 590), (245, 585)]}   # right (north) jamb, left (south) jamb
# (time range, take-4 track ids to skip): cam_1 1 = P4 seated behind the glass, 3 = poster of a man on the
# classroom wall (false positive); cam_2 1 = P4 seated.
FIT_WINDOWS = {"cam_1": ((7.5, 24.0), {1, 3}),
               "cam_2": ((10.5, 27.0), {1})}


def fit_height_horizon(cam):
    """(horizon_row, camera_height_m, n_boxes) from upright, unclipped person boxes in data/tracks/<cam>.json."""
    (t0, t1), skip = FIT_WINDOWS[cam]
    rows = []
    for tr in json.loads((REPO / "data" / "tracks" / f"{cam}.json").read_text(encoding="utf-8"))["tracks"]:
        if tr["global_id"] in skip:
            continue
        for k in tr["keyframes"]:
            x, y, w, h = k["box"]
            if not t0 <= k["t"] <= t1 or x < 0.01 or x + w > 0.99 or y < 0.01 or y + h > 0.995:
                continue
            if h * FRAME_H < 2.2 * w * FRAME_W:   # keep upright boxes only
                continue
            rows.append(((y + h) * FRAME_H, h * FRAME_H))
    v, hp = np.array(rows).T
    A = np.c_[np.ones_like(hp), hp]
    coef = np.linalg.lstsq(A, v, rcond=None)[0]
    keep = np.abs(A @ coef - v) <= np.quantile(np.abs(A @ coef - v), 0.8)   # drop the worst 20 % (bending, partly hidden)
    vh, k = np.linalg.lstsq(A[keep], v[keep], rcond=None)[0]
    return float(vh), float(k * PERSON_H), len(v)


def cam_frame(u, v, vh, hc):
    """Floor pixel -> (forward, left) metres in the camera's ground frame."""
    d = F * hc / (v - vh)
    return d, (FRAME_W / 2 - u) * d / F


def model(cam):
    """Ground model of one camera: horizon, height, yaw and map position, all derived from the door."""
    vh, hc, n = fit_height_horizon(cam)
    (a, b) = [np.array(cam_frame(u, v, vh, hc)) for u, v in DOOR_JAMBS[cam]]   # jambs north -> south
    fwd_l = b - a                                    # wall direction (north -> south) in (forward, left)
    # forward = (cx, cy), left = (cy, -cx) on the map (x east, y south); the wall must point to +y.
    ang = np.arctan2(fwd_l[0], -fwd_l[1])            # yaw that makes the jamb-to-jamb vector point along +y
    cx, cy = np.cos(ang), np.sin(ang)
    to_map = lambda p: np.array([p[0] * cx + p[1] * cy, p[0] * cy - p[1] * cx])
    cam_pos = DOOR_C_M - to_map((a + b) / 2)
    return {"cam_id": cam, "horizon_row": vh, "height_m": hc, "boxes_used": n, "yaw_deg": float(np.degrees(ang)),
            "door_width_m": float(np.linalg.norm(fwd_l)), "position_m": cam_pos, "to_map": to_map}


def pixel_to_map(m, u, v):
    p = m["position_m"] + m["to_map"](np.array(cam_frame(u, v, m["horizon_row"], m["height_m"])))
    return float(p[0] * SX), float(p[1] * SY)


# Four floor pixels per camera, all below the wall base, spread over the visible floor.
PAIR_PIXELS = {"cam_1": ((300, 715), (1100, 715), (700, 640), (1000, 600)),
               "cam_2": ((150, 715), (1150, 715), (380, 640), (900, 640))}


def point_pairs(cam, pixels=None):
    """Four image/map pairs generated from the ground model."""
    m = model(cam)
    pixels = PAIR_PIXELS[cam] if pixels is None else pixels
    return m, [list(p) for p in pixels], [[round(c, 4) for c in pixel_to_map(m, *p)] for p in pixels]


if __name__ == "__main__":
    for cam in DOOR_JAMBS:
        m, img, mp = point_pairs(cam)
        print(f"{cam}: horizon {m['horizon_row']:.0f}px, height {m['height_m']:.2f} m from {m['boxes_used']} boxes, "
              f"yaw {m['yaw_deg']:.0f} deg, door {m['door_width_m']:.2f} m wide, at map "
              f"({m['position_m'][0] * SX:.3f}, {m['position_m'][1] * SY:.3f})")
        print("   image_points", img, "\n   map_points  ", mp)
