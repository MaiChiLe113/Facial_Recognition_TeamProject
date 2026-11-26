"""Turn tape distances into x, y floor coordinates (metres, origin = floor point under CAM 1).

Only a few things are measured along axes; everything else is a straight tape distance
between two points (marker to marker, marker to door jamb, ...). The script solves all
points at once by least squares (trilateration, i.e. Pythagoras in 2D), so a point needs
distances to at least 2 already-located points, 3 to be checked.

Input: data/result.yaml (fill in the numbers; "A-B: 1.23" = tape from A to B).
Output: data/result_solved.json + a table with the error of every
point and of every tape distance.

Run: python ml/aruco/survey.py [path/to/result.yaml]
"""
import json
import sys
from pathlib import Path

import numpy as np
import yaml
from scipy.optimize import least_squares

DATA = Path(__file__).resolve().parent / "data"
TAPE_SIGMA = 0.01          # assumed tape error, metres
BAD_STD = 0.05             # flag points whose position is uncertain by more than this
BAD_RESID = 0.03           # flag tape distances that disagree with the solution by more than this

# Rough planned positions (metres from CAM 1, from figures/plan_A..D.png); only used to pick the
# right side of each triangle, never as a measurement.
GUESS = {
    "M0": [3.91, 3.31], "M2": [4.82, 4.22], "M3": [2.65, 2.96],
    "M4": [1.97, 0.86], "M5": [0.82, 1.77], "M6": [1.62, 2.47], "M7": [2.65, 3.59],
    "D1": [3.33, -0.85], "D3": [3.33, 0.18], "D5": [3.33, 1.17], "D7": [3.33, 2.19],
    "CAM2": [7.74, 3.13],
}
WALL_KEYS = ("glass_top", "glass_bottom", "door_top", "door_bottom")


def load(path):
    """result.yaml (flat 'A-B: d' lines) -> the dict solve() uses. A .json in the old format also works."""
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    y = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    num = lambda v: None if v in (None, "") else float(v)
    return {
        "x_wall": num(y.get("x_wall")),
        "wall_thickness": num(y.get("wall_thickness")),
        "along_wall": {k: num(y.get(k)) for k in WALL_KEYS},
        "desk_size": {"L": num(y.get("desk_L")), "W": num(y.get("desk_W"))},
        "desk_height": num(y.get("desk_height")),
        "cam_heights": {"cam_1": num(y.get("cam1_height")), "cam_2": num(y.get("cam2_height"))},
        "distances": [[*k.split("-", 1), num(v)] for k, v in y.items() if "-" in str(k)],
        "guess": GUESS,
    }


def fixed_points(s):
    """Points with known coordinates: origin, P0, and the wall points measured along the wall."""
    xw = s["x_wall"]
    t = s.get("wall_thickness") or 0.0
    pts = {"O": (0.0, 0.0)}
    if xw is None:
        return pts
    pts["P0"] = (xw, 0.0)
    pts["P0_in"] = (xw + t, 0.0)
    for name, y in s["along_wall"].items():
        if y is not None:
            pts[name] = (xw, y)              # corridor face of the wall
            pts[name + "_in"] = (xw + t, y)  # room face of the wall (wall thickness)
    return pts


def solve(s):
    fixed = fixed_points(s)
    guess = {k: tuple(v) for k, v in s["guess"].items()}
    pairs = [(a, b, d) for a, b, d in s["distances"] if d is not None]
    skipped = [(a, b) for a, b, d in s["distances"] if d is None]

    unknown = sorted({p for a, b, _ in pairs for p in (a, b) if p not in fixed})
    for p in unknown:
        if p not in guess:
            sys.exit(f"no rough position for '{p}' in \"guess\" (needed to pick the right side)")
    count = {p: sum(p in (a, b) for a, b, _ in pairs) for p in unknown}
    few = [p for p in unknown if count[p] < 2]
    if few:
        print(f"WARNING: these points have fewer than 2 distances and cannot be located: {few}")
        unknown = [p for p in unknown if p not in few]
        pairs = [(a, b, d) for a, b, d in pairs if a not in few and b not in few]
    idx = {p: i for i, p in enumerate(unknown)}

    def pos(v, p):
        return np.array(fixed[p]) if p in fixed else v[2 * idx[p]: 2 * idx[p] + 2]

    def resid(v):
        return np.array([np.linalg.norm(pos(v, a) - pos(v, b)) - d for a, b, d in pairs])

    x0 = np.concatenate([guess[p] for p in unknown]) if unknown else np.zeros(0)
    if not unknown:
        return fixed, {}, pairs, np.zeros(0), skipped, {}
    r = least_squares(resid, x0)
    v = r.x
    # position uncertainty from the Jacobian (tape error TAPE_SIGMA on every distance)
    J = r.jac
    try:
        cov = np.linalg.inv(J.T @ J) * TAPE_SIGMA ** 2
        std = {p: float(np.sqrt(cov[2 * i, 2 * i] + cov[2 * i + 1, 2 * i + 1])) for p, i in idx.items()}
    except np.linalg.LinAlgError:
        std = {p: float("inf") for p in unknown}
    solved = {p: tuple(map(float, pos(v, p))) for p in unknown}
    return fixed, solved, pairs, resid(v), skipped, std


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "result.yaml"
    s = load(src)
    if s["x_wall"] is None:
        sys.exit("fill in x_wall first (tape from the origin straight to the room wall)")
    fixed, solved, pairs, res, skipped, std = solve(s)

    print("Points (metres, origin = floor under CAM 1, x -> room, y -> door)")
    for p, (x, y) in fixed.items():
        print(f"  {p:16s} x {x:6.2f}  y {y:6.2f}   measured")
    for p, (x, y) in sorted(solved.items()):
        flag = "  <- uncertain: add a distance from another direction" if std[p] > BAD_STD else ""
        print(f"  {p:16s} x {x:6.2f}  y {y:6.2f}   +/- {std[p]:.3f}{flag}")

    print("\nTape distances (measured vs solved)")
    for (a, b, d), e in zip(pairs, res):
        flag = "  <- check this one (typo, wrong marker or tape not straight?)" if abs(e) > BAD_RESID else ""
        print(f"  {a:>12s} - {b:<12s} {d:6.2f}  error {e:+.3f}{flag}")
    if skipped:
        print(f"\nNot measured yet ({len(skipped)}): " + ", ".join(f"{a}-{b}" for a, b in skipped))

    L, W = s["desk_size"]["L"], s["desk_size"]["W"]
    desks = {k: [x, y, L, W] for k, (x, y) in solved.items() if k.startswith("D") and k[1:].isdigit()}
    out = {"_note": f"generated by survey.py from {src.name}; metres, origin = floor under CAM 1",
           "points": {**{k: list(v) for k, v in fixed.items()}, **{k: list(v) for k, v in solved.items()}},
           "std": std, "desks_xywh": desks, "desk_height": s.get("desk_height"),
           "cam_heights": s.get("cam_heights"),
           "markers": {k[1:]: list(v) for k, v in solved.items() if k.startswith("M")}}
    dst = src.with_name(src.stem + "_solved.json")
    dst.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nWrote {dst}")


if __name__ == "__main__":
    main()
