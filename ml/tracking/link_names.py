"""Carry names from the attendance camera to cam_1 / cam_2 (door handoff).  Owner: Mai Chi

A person is named only at check-in, on the attendance camera (ml/face_recognition/name_tracks.py).
At that moment they stand in the doorway, where cam_1 (outside) and cam_2 (inside) also see them.
For every named attendance_cam track this script looks, in cam_1 and cam_2, for the track whose feet
(mapped to the Room 204 floor map with data/calibration/<cam>_homography.json) are at the door while the
attendance track is visible (+-DOOR_WINDOW_S). If exactly one track is there, it gets the same name;
"name_from" = the check-in time (or the track's start, if later), so the UI shows the name only after
check-in. Ambiguous cases (two or more people at the door) are left unnamed and reported.

Stand-in for the Re-ID matcher (Phase B): it only names the track that was at the door, not later
tracks of the same person (e.g. after an occlusion or seen through the glass).

Run after precompute_tracks.py and name_tracks.py:
    ml/.venv/bin/python ml/tracking/link_names.py --take all
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from paths import configured_take, video_config

REPO = Path(__file__).resolve().parents[2]
CAMS = ("cam_1", "cam_2")
DOOR_X, DOOR_Y = (0.2, 0.4), (0.7, 1.05)   # map area around the classroom door (door at x 0.3, y 0.79-0.96)
DOOR_WINDOW_S = 1.5                          # how far outside the attendance track's time span to look
MIN_DOOR_KEYFRAMES = 3                       # keyframes at the door needed to count as "at the door"


def load(take, cam):
    return json.loads((REPO / "data" / "tracks" / f"take{take}" / f"{cam}.json").read_text(encoding="utf-8"))


def feet_on_map(box, H):
    """Map position of the box's bottom-centre, or None when the feet are cut off by the frame edge."""
    x, y, w, h = box
    if y + h >= 0.995:
        return None
    p = cv2.perspectiveTransform(np.array([[[(x + w / 2) * 1280, (y + h) * 720]]], dtype=np.float64), H)[0, 0]
    return float(p[0]), float(p[1])


def at_door(track, H, t0, t1):
    """Number of keyframes in [t0, t1] where the track's feet are in the door area."""
    n = 0
    for k in track["keyframes"]:
        if t0 <= k["t"] <= t1 and (p := feet_on_map(k["box"], H)) is not None:
            n += DOOR_X[0] <= p[0] <= DOOR_X[1] and DOOR_Y[0] <= p[1] <= DOOR_Y[1]
    return n


def link_take(take):
    H = {c: np.array(json.loads((REPO / "data" / "calibration" / f"{c}_homography.json").read_text())["H"])
         for c in CAMS}
    att = load(take, "attendance_cam")["tracks"]
    report = []
    for cam in CAMS:
        data = load(take, cam)
        for tr in data["tracks"]:                      # start clean: names here only come from this script
            tr["name"] = None
            tr.pop("name_from", None)
            tr.pop("name_source", None)
        for a in att:
            if not a.get("name"):
                continue
            t0, t1 = a["keyframes"][0]["t"] - DOOR_WINDOW_S, a["keyframes"][-1]["t"] + DOOR_WINDOW_S
            scores = sorted(((at_door(tr, H[cam], t0, t1), tr) for tr in data["tracks"]), key=lambda s: -s[0])
            cands = [(n, tr) for n, tr in scores if n >= MIN_DOOR_KEYFRAMES]
            if len(cands) != 1:
                report.append(f"take {take} {cam}: {a['name']} not carried over, "
                              f"{len(cands)} tracks at the door ({[tr['global_id'] for _, tr in cands]})")
                continue
            n, tr = cands[0]
            check_in = a.get("name_from", a["keyframes"][0]["t"])
            tr["name"] = a["name"]
            tr["name_from"] = max(check_in, tr["keyframes"][0]["t"])
            tr["name_source"] = f"attendance_cam ID {a['global_id']} (door handoff)"
            report.append(f"take {take} {cam}: ID {tr['global_id']} = {a['name']} from t={tr['name_from']} s "
                          f"({n} keyframes at the door while attendance ID {a['global_id']} was visible)")
        (REPO / "data" / "tracks" / f"take{take}" / f"{cam}.json").write_text(json.dumps(data, indent=1),
                                                                               encoding="utf-8")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--take", default=None, help="take number or 'all' (default: the configured take)")
    a = p.parse_args()
    takes = ([t["take"] for t in video_config()["takes"]] if a.take == "all"
             else [configured_take() if a.take is None else int(a.take)])
    for t in takes:
        for line in link_take(t) or [f"take {t}: no named attendance_cam track"]:
            print(line)
