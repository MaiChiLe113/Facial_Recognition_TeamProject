"""Tracks (boxes in camera frames) -> trajectories on the Room 204 floor map.  Owner: Đức Mạnh

For every keyframe of a cam_1 / cam_2 track: feet = bottom-centre of the box, projected with the camera's
homography to map fractions (x 0 left -> 1 right, y 0 top -> 1 bottom, room204_map.json convention).
Keyframes whose feet are cut off by the bottom edge of the frame are dropped (same rule as
ml/tracking/link_names.py). The path is smoothed with a sliding median and every point gets a zone:
corridor (x < wall), door (near the door opening), room.

    python ml/presence_verification/trajectories.py --take all      # writes outputs/trajectories/take<N>.json
"""
import argparse

import numpy as np

from pv_common import FRAME_H, FRAME_W, MAP_CAMS, OUTPUTS, homography, load_tracks, room_map, takes, write_json

FEET_CUT = 0.995          # box bottom at or below this fraction of the frame = feet not visible
SMOOTH_S = 0.5            # sliding-median window (seconds)
DOOR_MARGIN_X = 0.08      # map units either side of the wall that still count as "at the door"
DOOR_MARGIN_Y = 0.08      # extra map units above/below the door opening (homography is only estimated)
MIN_POINTS = 3            # tracks with fewer usable points are ignored

# Where each camera's floor homography can be trusted (map x range). cam_1 stands in the corridor and also
# sees into the room through the glass, but people seen through the glass are not on its floor plane;
# cam_2 stands in the room and also "sees" a poster in the corridor. Points outside are dropped, not clipped.
VALID_X = {"cam_1": (-0.02, 0.36), "cam_2": (0.25, 1.02)}
VALID_Y = (-0.02, 1.05)


def to_map(cam_id, box):
    """Map position (x, y) of a normalised box [x, y, w, h], or None when the feet are not visible or the
    point falls outside the part of the map this camera's homography is valid for."""
    if cam_id not in MAP_CAMS:
        return None
    x, y, w, h = (float(v) for v in box[:4])
    if y + h >= FEET_CUT:
        return None
    p = homography(cam_id) @ np.array([(x + w / 2) * FRAME_W, (y + h) * FRAME_H, 1.0])
    if abs(p[2]) < 1e-12:
        return None
    mx, my = float(p[0] / p[2]), float(p[1] / p[2])
    lo, hi = VALID_X[cam_id]
    if not (lo <= mx <= hi and VALID_Y[0] <= my <= VALID_Y[1]):
        return None
    return mx, my


def zone_of(x, y):
    m = room_map()
    wall, (d0, d1) = m["corridor_wall_x"], m["door"]["y"]
    if abs(x - wall) <= DOOR_MARGIN_X and d0 - DOOR_MARGIN_Y <= y <= d1 + DOOR_MARGIN_Y:
        return "door"
    return "corridor" if x < wall else "room"


def _median_smooth(ts, values, window):
    out = np.empty_like(values)
    for i, t in enumerate(ts):
        sel = np.abs(ts - t) <= window / 2
        out[i] = np.median(values[sel], axis=0)
    return out


def track_points(cam_id, track, smooth_s=SMOOTH_S):
    """[{t, x, y, zone}] of one track, smoothed, sorted by time."""
    raw = [(k["t"], to_map(cam_id, k["box"])) for k in track.get("keyframes", [])]
    raw = [(t, p) for t, p in raw if p is not None and all(np.isfinite(p))]
    if len(raw) < MIN_POINTS:
        return []
    ts = np.array([t for t, _ in raw], dtype=float)
    xy = np.array([p for _, p in raw], dtype=float)
    if smooth_s:
        xy = _median_smooth(ts, xy, smooth_s)
    return [{"t": round(float(t), 3), "x": round(float(x), 4), "y": round(float(y), 4), "zone": zone_of(x, y)}
            for t, (x, y) in zip(ts, xy)]


def take_trajectories(take, smooth_s=SMOOTH_S):
    """All map trajectories of one take: [{cam_id, track_id, name, points: [...]}, ...]."""
    out = []
    for cam in MAP_CAMS:
        for tr in load_tracks(take, cam):
            pts = track_points(cam, tr, smooth_s)
            if pts:
                out.append({"cam_id": cam, "track_id": tr["global_id"], "name": tr.get("name"),
                            "name_from": tr.get("name_from"), "points": pts})
    return out


def flat_points(trajectories):
    """Trajectories -> the flat point list of the infer.py contract: [{t, track_id, cam_id, x, y}]."""
    return [{"t": p["t"], "track_id": f"{tr['cam_id']}:{tr['track_id']}", "cam_id": tr["cam_id"],
             "x": p["x"], "y": p["y"]} for tr in trajectories for p in tr["points"]]


def plot_take(take, path):
    """Optional picture for checking by eye (needs matplotlib)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    m = room_map()
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.axvline(m["corridor_wall_x"], color="k", lw=1)
    ax.plot([m["door"]["x"]] * 2, m["door"]["y"], color="tab:green", lw=6, alpha=.5, label="door")
    for tr in take_trajectories(take):
        xs, ys = [p["x"] for p in tr["points"]], [p["y"] for p in tr["points"]]
        ax.plot(xs, ys, "-" if tr["cam_id"] == "cam_2" else "--", lw=1.2,
                label=f"{tr['cam_id']} {tr['track_id']} {tr['name'] or ''}".strip())
        ax.plot(xs[0], ys[0], "o", ms=3, color="k")
    ax.set(xlim=(0, 1), ylim=(1, 0), title=f"Take {take}: feet on the map (o = start)", xlabel="x", ylabel="y")
    ax.legend(fontsize=6, loc="upper right")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--take", default="all", help="take number or 'all'")
    ap.add_argument("--plot", action="store_true", help="also save outputs/trajectories/take<N>.png (matplotlib)")
    a = ap.parse_args()
    for t in (takes() if a.take == "all" else [int(a.take)]):
        traj = take_trajectories(t)
        path = write_json(OUTPUTS / "trajectories" / f"take{t}.json", {"take": t, "trajectories": traj})
        print(f"take {t}: {len(traj)} trajectories, {sum(len(x['points']) for x in traj)} points -> {path.name}")
        if a.plot:
            try:
                print("  plot:", plot_take(t, OUTPUTS / "trajectories" / f"take{t}.png"))
            except ImportError:
                print("  plot skipped: pip install matplotlib")
