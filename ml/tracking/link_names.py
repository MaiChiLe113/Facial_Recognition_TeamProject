"""Carry names from the attendance camera to cam_1 / cam_2 (door handoff).  Owner: Mai Chi

A person is named only at check-in, on the attendance camera (ml/face_recognition/name_tracks.py).
At that moment they stand in the doorway, where cam_1 (outside) and cam_2 (inside) also see them.
For every named attendance_cam track this script looks, in cam_1 and cam_2, for the track whose feet
(mapped to the Room 204 floor map with data/calibration/<cam>_homography.json) are at the door while the
attendance track is visible (+-DOOR_WINDOW_S). If exactly one track is there, it gets the same name;
"name_from" = the check-in time (or the track's start, if later), so the UI shows the name only after
check-in.

Several people at the door together (take 3: three students check in side by side) make the door test ambiguous.
Then each (name, candidate track) pair is scored by clothing colour (torso colour histogram on the attendance
camera vs. on cam_1 / cam_2, see torso_colour) plus time overlap (the track's time at the door vs. the attendance
track's time span), the best joint assignment is found, and a pair is kept only if it beats every other option for
that name and for that track by MARGIN. Pairs that are not clearly better stay unnamed and are reported: no name
rather than a wrong one.

Stand-in for the Re-ID matcher (Phase B): it only names the track that was at the door, not later
tracks of the same person (e.g. after an occlusion or seen through the glass).

Run after precompute_tracks.py and name_tracks.py:
    ml/.venv/bin/python ml/tracking/link_names.py --take all
"""
import argparse
import itertools
import json
from pathlib import Path

import cv2
import numpy as np

from paths import configured_take, video_config, video_path
from room_tracker import carry_names

REPO = Path(__file__).resolve().parents[2]
CAMS = ("cam_1", "cam_2")
DOOR_X, DOOR_Y = (0.2, 0.4), (0.7, 1.05)   # map area around the classroom door (door at x 0.3, y 0.79-0.96)
DOOR_WINDOW_S = 1.5                          # how far outside the attendance track's time span to look
MIN_DOOR_KEYFRAMES = 3                       # keyframes at the door needed to count as "at the door"
# Several people at the door (see the module docstring):
COLOUR_SAMPLES = 12                          # keyframes sampled per track for its colour histogram
ATT_TORSO = ((0.2, 0.8), (0.55, 1.0))        # torso inside an attendance_cam person box (x, y fractions): close-up
CAM_TORSO = ((0.25, 0.75), (0.2, 0.5))       # torso inside a full-body cam_1 / cam_2 person box
MIN_COLOUR = 0.4                             # a pair needs at least this colour similarity (1 - Bhattacharyya)
MARGIN = 0.15                                # ... and a score this much above every other option for name and track


def load(take, cam):
    return json.loads((REPO / "data" / "tracks" / f"take{take}" / f"{cam}.json").read_text(encoding="utf-8"))


def feet_on_map(box, H):
    """Map position of the box's bottom-centre, or None when the feet are cut off by the frame edge."""
    x, y, w, h = box
    if y + h >= 0.995:
        return None
    p = cv2.perspectiveTransform(np.array([[[(x + w / 2) * 1280, (y + h) * 720]]], dtype=np.float64), H)[0, 0]
    return float(p[0]), float(p[1])


def door_keyframes(track, H, t0, t1):
    """The track's keyframes in [t0, t1] with the feet in the door area."""
    return [k for k in track["keyframes"] if t0 <= k["t"] <= t1 and (p := feet_on_map(k["box"], H)) is not None
            and DOOR_X[0] <= p[0] <= DOOR_X[1] and DOOR_Y[0] <= p[1] <= DOOR_Y[1]]


def torso_colour(cap, keyframes, region):
    """Normalised 16-bin colour histogram of the torso over up to COLOUR_SAMPLES keyframes, or None.
    Each frame is white-balanced first (grey world: the cameras' colour casts differ). Saturated pixels count
    in 12 hue bins; grey / black / white pixels (hue meaningless) in 4 brightness bins, so a grey T-shirt and a
    navy jersey do not look alike just because their noisy hues happen to match."""
    hist = np.zeros(16)
    for k in keyframes[::max(1, len(keyframes) // COLOUR_SAMPLES)]:
        cap.set(cv2.CAP_PROP_POS_MSEC, k["t"] * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        fh, fw = frame.shape[:2]
        x, y, w, h = k["box"]
        (rx0, rx1), (ry0, ry1) = region
        crop = frame[int((y + h * ry0) * fh):int((y + h * ry1) * fh), int((x + w * rx0) * fw):int((x + w * rx1) * fw)]
        if crop.size < 300:
            continue
        grey = frame.reshape(-1, 3).mean(0)
        crop = np.clip(crop * (grey.mean() / np.maximum(grey, 1)), 0, 255).astype(np.uint8)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(int)
        chroma = (hsv[:, 1] >= 70) & (hsv[:, 2] >= 50)
        bins = np.concatenate([hsv[chroma, 0] * 12 // 180, 12 + np.minimum(hsv[~chroma, 2] * 4 // 256, 3)])
        hist += np.bincount(bins, minlength=16)
    return hist / hist.sum() if hist.sum() else None


def colour_similarity(a, b):
    return 1.0 - cv2.compareHist(a.astype("float32"), b.astype("float32"), cv2.HISTCMP_BHATTACHARYYA)


def time_overlap(span, keyframes):
    """IoU of the attendance span (t0, t1) and the time the track spends at the door."""
    d0, d1 = keyframes[0]["t"], keyframes[-1]["t"]
    inter = max(0.0, min(span[1], d1) - max(span[0], d0))
    return inter / (max(span[1], d1) - min(span[0], d0) or 1.0)


def resolve_crowded_door(take, cam, crowded, att_colour):
    """crowded: {name: {"span", "check_in", "cands": [(n_door_keyframes, track, door_keyframes)]}} for names with
    several tracks at the door. Returns [(name, track, colour, overlap, score, margin)] of the confident pairs and
    report lines for the rest."""
    cap = cv2.VideoCapture(str(video_path(cam, take)))
    tracks = {tr["global_id"]: (tr, kfs) for g in crowded.values() for _, tr, kfs in g["cands"]}
    colour = {tid: torso_colour(cap, kfs, CAM_TORSO) for tid, (_, kfs) in tracks.items()}
    cap.release()
    score = {}
    for name, g in crowded.items():
        for _, tr, kfs in g["cands"]:
            tid = tr["global_id"]
            if att_colour.get(name) is None or colour[tid] is None:
                continue
            c = colour_similarity(att_colour[name], colour[tid])
            o = time_overlap(g["span"], kfs)
            score[name, tid] = (c, o, c + o)
    names, tids = list(crowded), list(tracks)
    best, best_total = [], -1.0                      # joint assignment: each name one track, each track one name
    for perm in itertools.permutations(tids + [None] * len(names), len(names)):
        pairs = [(n, t) for n, t in zip(names, perm) if t is not None and (n, t) in score]
        total = sum(score[p][2] for p in pairs)
        if total > best_total:
            best, best_total = pairs, total
    kept, report = [], []
    for name, tid in best:
        c, o, s = score[name, tid]
        rivals = [v[2] for (n, t), v in score.items() if (n == name) != (t == tid)]
        margin = s - max(rivals, default=0.0)
        if c >= MIN_COLOUR and margin >= MARGIN:
            kept.append((name, tracks[tid][0], c, o, s, margin))
        else:
            report.append(f"take {take} {cam}: {name} not carried over, best track ID {tid} not clear enough "
                          f"(colour {c:.2f}, time overlap {o:.2f}, margin {margin:.2f} < {MARGIN})")
    for name in set(names) - {n for n, _ in best}:
        report.append(f"take {take} {cam}: {name} not carried over, no track left to assign")
    return kept, report


def link_take(take):
    H = {c: np.array(json.loads((REPO / "data" / "calibration" / f"{c}_homography.json").read_text())["H"])
         for c in CAMS}
    att = load(take, "attendance_cam")["tracks"]
    # One entry per name: a person whose attendance track was split (ID switch) is one person, not two.
    people = {}
    for a in att:
        if a.get("name"):
            p = people.setdefault(a["name"], {"tracks": [], "check_in": a.get("name_from", a["keyframes"][0]["t"])})
            p["tracks"].append(a)
            p["check_in"] = min(p["check_in"], a.get("name_from", a["keyframes"][0]["t"]))
    att_colour = {}
    report = []
    datas = {}
    for cam in CAMS:
        data = load(take, cam)
        for tr in data["tracks"]:                      # start clean: names here only come from this script
            tr["name"] = None
            tr.pop("name_from", None)
            tr.pop("name_source", None)
        crowded = {}
        for name, p in people.items():
            span = (min(a["keyframes"][0]["t"] for a in p["tracks"]), max(a["keyframes"][-1]["t"] for a in p["tracks"]))
            t0, t1 = span[0] - DOOR_WINDOW_S, span[1] + DOOR_WINDOW_S
            cands = sorted(((len(kfs), tr, kfs) for tr in data["tracks"] if (kfs := door_keyframes(tr, H[cam], t0, t1))),
                           key=lambda c: -c[0])
            cands = [c for c in cands if c[0] >= MIN_DOOR_KEYFRAMES]
            ids = ", ".join(str(a["global_id"]) for a in p["tracks"])
            if len(cands) == 1:
                n, tr, _ = cands[0]
                tr["name"] = name
                tr["name_from"] = max(p["check_in"], tr["keyframes"][0]["t"])
                tr["name_source"] = f"attendance_cam ID {ids} (door handoff)"
                report.append(f"take {take} {cam}: ID {tr['global_id']} = {name} from t={tr['name_from']} s "
                              f"({n} keyframes at the door while attendance ID {ids} was visible)")
            elif cands:
                crowded[name] = {"span": span, "check_in": p["check_in"], "cands": cands, "ids": ids}
            else:
                report.append(f"take {take} {cam}: {name} not carried over, no track at the door")
        if crowded:
            for name in crowded:
                if name not in att_colour:
                    cap = cv2.VideoCapture(str(video_path("attendance_cam", take)))
                    att_colour[name] = torso_colour(cap, [k for a in people[name]["tracks"] for k in a["keyframes"]],
                                                    ATT_TORSO)
                    cap.release()
            taken = {tr["global_id"] for tr in data["tracks"] if tr["name"]}
            for g in crowded.values():
                g["cands"] = [c for c in g["cands"] if c[1]["global_id"] not in taken]
            kept, lines = resolve_crowded_door(take, cam, crowded, att_colour)
            report += lines
            for name, tr, c, o, s, margin in kept:
                tr["name"] = name
                tr["name_from"] = max(crowded[name]["check_in"], tr["keyframes"][0]["t"])
                tr["name_source"] = f"attendance_cam ID {crowded[name]['ids']} (door handoff, crowded: colour + time)"
                report.append(f"take {take} {cam}: ID {tr['global_id']} = {name} from t={tr['name_from']} s "
                              f"(crowded door: colour {c:.2f}, time overlap {o:.2f}, margin {margin:.2f})")
        datas[cam] = data
    # Names that survive a broken track: room occupancy (room_tracker.py), after every door handoff is known.
    at_door = lambda cam, kfs: sum(1 for k in kfs if (p := feet_on_map(k["box"], H[cam])) is not None
                                   and DOOR_X[0] <= p[0] <= DOOR_X[1] and DOOR_Y[0] <= p[1] <= DOOR_Y[1]) >= 2
    report += carry_names(take, {n: p["check_in"] for n, p in people.items()},
                          {cam: d["tracks"] for cam, d in datas.items()}, at_door)
    for tr in datas["cam_2"]["tracks"]:            # the roster counts a person as "Left" only through the door
        tr["ends_at_door"] = at_door("cam_2", tr["keyframes"][-3:])
    for cam, data in datas.items():
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
