"""Floor points of the markers on a camera photo: you click only the ones OpenCV cannot read.

Markers OpenCV reads are filled in automatically: flat = centre of the black square; standing =
bottom edge of the paper, extrapolated from the square (A4 sheets of markers/*.png, printed at 100%,
standing on their bottom edge). It may fall just outside the frame; that is fine. A bent, held
or tilted sheet makes it wrong by several pixels: check data/pins_<camera>_check.png and re-click with --fix.

  python ml/aruco/pin_points.py cam1        # cam1_fixed.jpg -> pins_cam1.json
  python ml/aruco/pin_points.py cam2        # cam2_fixed.jpg -> pins_cam2.json
  python ml/aruco/pin_points.py cam2 --fix M0  # re-click an automatic point that is off (M0,M6 for several)
  python ml/aruco/pin_points.py cam1 --doors   # also ask for the two optional door corners

Always click where the point TOUCHES THE FLOOR:
  standing marker = middle of the BOTTOM EDGE OF THE PAPER (not of the black square)
  flat marker     = centre of the black square (where its diagonals cross)

Keys: left click = place    i j k l = move 1 px    Enter / Space = confirm, next point
      s = skip (point not visible)    u = back one point    q / Esc = save and quit
Running it again loads your saved clicks; press Enter to keep one.
Then  python ml/aruco/fit_floor.py  fits the camera to these pins and prints the error of each one.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from check_aruco import detect

DATA = Path(__file__).resolve().parent / "data"
STAND = "standing: middle of the BOTTOM EDGE OF THE PAPER"
FLAT = "flat: CENTRE of the black square"
CORNER = "optional: where this door edge meets the floor (s = not visible)"
CAMERAS = {
    "cam1": ("cam1_fixed.jpg", [
        ("M3", STAND), ("M4", STAND), ("M5", STAND), ("M6", STAND), ("M7", STAND),
        ("door_top", CORNER + ", corridor side, next to M3"),
        ("door_bottom", CORNER + ", corridor side, next to M7")]),
    "cam2": ("cam2_fixed.jpg", [
        ("M0", STAND), ("M2", FLAT), ("M3", STAND), ("M7", STAND),
        ("door_top_in", CORNER + ", room side, next to M3"),
        ("door_bottom_in", CORNER + ", room side, next to M7")]),
}
PAPER_GAP = 0.512   # black square -> bottom of the A4 sheet, in square sides (measured on markers/*.png)
ZOOM, HALF = 8, 20          # magnifier: (2*HALF+1) px square, ZOOM times bigger


def auto_points(img, points):
    """Floor pixel of every expected marker that OpenCV reads."""
    found = detect(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(float)
    unit = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])     # marker corners: TL, TR, BR, BL
    out = {}
    for name, hint in points:
        if not name.startswith("M") or int(name[1:]) not in found:
            continue
        H = cv2.getPerspectiveTransform(unit, np.float32(found[int(name[1:])][0]))
        spot = [0.5, 0.5] if hint == FLAT else [0.5, 1 + PAPER_GAP]
        x, y = cv2.perspectiveTransform(np.float32([[spot]]), H)[0, 0]
        x, y = round(float(x)), round(float(y))
        if hint != FLAT:
            y = paper_bottom(hsv, x, y)
        out[name] = [x, y]
    return out


def paper_bottom(hsv, x, y, reach=15):
    """Snap a standing marker's estimated paper bottom to the white-paper -> floor edge below the
    marker centre (the sheet is often bent or tilted, which the extrapolation does not know).
    Keeps the estimate when no edge is found (e.g. the bottom is outside the frame)."""
    h, w = hsv.shape[:2]
    if not (3 <= x < w - 3):
        return y
    S, V = hsv[:, x - 3:x + 4, 1].mean(1), hsv[:, x - 3:x + 4, 2].mean(1)
    edges = [yy for yy in range(max(3, y - reach), min(h - 4, y + reach))
             if S[yy - 3:yy].mean() < 25 and V[yy - 3:yy].mean() > 120              # white paper above
             and S[yy + 1:yy + 4].mean() > max(18, S[yy - 3:yy].mean() + 12)]       # floor below
    if not edges:
        return y
    best = min(edges, key=lambda yy: abs(yy - y))
    while best - 1 in edges:          # an edge passes the test on a few rows: take its top row
        best -= 1
    return best


def draw(img, pins, name, hint, mouse):
    view = img.copy()
    for k, (x, y) in pins.items():
        col = (0, 0, 255) if k == name else (0, 200, 0)
        cv2.drawMarker(view, (x, y), col, cv2.MARKER_CROSS, 14, 1)
        cv2.putText(view, k, (x + 8, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
    h, w = img.shape[:2]
    # magnifier follows the mouse, drawn in a top corner away from it
    mx, my = mouse
    pad = cv2.copyMakeBorder(img, HALF, HALF, HALF, HALF, cv2.BORDER_CONSTANT)
    size = (2 * HALF + 1) * ZOOM
    lens = cv2.resize(pad[my:my + 2 * HALF + 1, mx:mx + 2 * HALF + 1], (size, size),
                      interpolation=cv2.INTER_NEAREST)
    c = HALF * ZOOM + ZOOM // 2
    if name in pins:                      # the pin placed for the current point
        px, py = (pins[name][0] - mx) * ZOOM + c, (pins[name][1] - my) * ZOOM + c
        cv2.drawMarker(lens, (px, py), (0, 0, 255), cv2.MARKER_CROSS, 24, 1)
    cv2.line(lens, (c, 0), (c, c - ZOOM), (0, 255, 255), 1)
    cv2.line(lens, (c, c + ZOOM), (c, size), (0, 255, 255), 1)
    cv2.line(lens, (0, c), (c - ZOOM, c), (0, 255, 255), 1)
    cv2.line(lens, (c + ZOOM, c), (size, c), (0, 255, 255), 1)
    x0 = w - size - 10 if mx < w // 2 else 10
    view[50:50 + size, x0:x0 + size] = lens
    cv2.rectangle(view, (x0, 50), (x0 + size, 50 + size), (0, 255, 255), 1)
    cv2.rectangle(view, (0, 0), (w, 42), (0, 0, 0), -1)
    cv2.putText(view, f"{name}  {hint}", (8, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(view, "click | ijkl nudge | Enter next | s skip | u back | q save+quit",
                (8, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    return view


def pin(img, points, pins):
    if not points:
        return pins
    h, w = img.shape[:2]
    state = {"i": 0, "mouse": (w // 2, h // 2)}

    def on_mouse(event, x, y, *_):
        x, y = min(max(x, 0), w - 1), min(max(y, 0), h - 1)
        state["mouse"] = (x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            pins[points[state["i"]][0]] = [x, y]

    win = "pin points"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)       # mouse x, y stay in image pixels when resized
    cv2.resizeWindow(win, w, h)
    cv2.setMouseCallback(win, on_mouse)
    nudge = {ord("i"): (0, -1), ord("k"): (0, 1), ord("j"): (-1, 0), ord("l"): (1, 0)}
    while state["i"] < len(points):
        name, hint = points[state["i"]]
        cv2.imshow(win, draw(img, pins, name, hint, state["mouse"]))
        key = cv2.waitKey(20) & 0xFF
        if key in (ord("q"), 27) or cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
            break
        if key in (13, 32) and name in pins:
            state["i"] += 1
        elif key == ord("s"):
            pins.pop(name, None)
            state["i"] += 1
        elif key == ord("u"):
            state["i"] = max(0, state["i"] - 1)
        elif key in nudge and name in pins:
            dx, dy = nudge[key]
            pins[name] = [pins[name][0] + dx, pins[name][1] + dy]
            state["mouse"] = tuple(pins[name])
    cv2.destroyAllWindows()
    return pins


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("camera", choices=CAMERAS)
    ap.add_argument("--doors", action="store_true", help="also ask for the optional door corners")
    ap.add_argument("--fix", default="", help="markers to click again even if known, e.g. M0,M6")
    a = ap.parse_args()
    fix = [k.strip() for k in a.fix.split(",") if k.strip()]
    image, points = CAMERAS[a.camera]
    img = cv2.imread(str(DATA / image))
    if img is None:
        raise SystemExit(f"cannot read {image}")
    unknown = set(fix) - {k for k, _ in points}
    if unknown:
        raise SystemExit(f"--fix: {a.camera} has no point {sorted(unknown)}")
    out = DATA / f"pins_{a.camera}.json"
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    auto = auto_points(img, points)
    manual = {k: v for k, v in old.get("points", {}).items() if k in old.get("manual", [])}
    todo = [(k, h) for k, h in points
            if k in fix or (k not in auto and k not in manual and (k.startswith("M") or a.doors))]
    print(f"Automatic: {sorted(set(auto) - set(manual)) or 'none'}    clicked earlier: {sorted(manual) or 'none'}")
    print(f"To click:  {[k for k, _ in todo] or 'nothing'}")
    pins = pin(img, todo, {**auto, **manual})
    # clicked = saved earlier, or asked for in this run and moved away from the automatic value
    asked = {k for k, _ in todo}
    manual_names = [k for k in pins if k in manual or (k in asked and pins[k] != auto.get(k))]
    missing = [k for k, _ in points if k.startswith("M") and k not in pins]
    if missing:
        print(f"WARNING: no pin for {missing}")
    if not pins:
        raise SystemExit("nothing pinned, nothing saved")
    out.write_text(json.dumps({"image": image, "size": [img.shape[1], img.shape[0]], "points": pins,
                               "manual": manual_names}, indent=1),
                   encoding="utf-8")
    print(f"Saved {len(pins)} pins to {out.name}: {pins}")
    view = cv2.copyMakeBorder(img, 0, 40, 0, 0, cv2.BORDER_CONSTANT)     # room for pins below the frame
    for k, (x, y) in pins.items():
        col = (0, 0, 255) if k in manual_names else (255, 0, 255)
        cv2.drawMarker(view, (x, y), col, cv2.MARKER_CROSS, 14, 1)
        cv2.putText(view, k, (x + 8, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    cv2.imwrite(str(DATA / f"pins_{a.camera}_check.png"), view)
    print(f"Look at data/pins_{a.camera}_check.png (red = clicked, magenta = automatic)")
    print("Next: python ml/aruco/fit_floor.py  (fits the camera, prints the error of each pin)")


if __name__ == "__main__":
    main()
