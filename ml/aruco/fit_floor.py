"""Image -> floor mapping per camera, from the tape survey and the pinned markers, plus pictures to check it.

  python ml/aruco/fit_floor.py              # fit both cameras, write data/floor_cam*.json and figures/*.png
  python ml/aruco/fit_floor.py click cam1   # click a floor spot on the photo -> x, y in metres (check with a tape)

Inputs:  result_solved.json (python ml/aruco/survey.py), pins_cam1.json / pins_cam2.json (python ml/aruco/pin_points.py)
Model: a pinhole camera (focal, yaw, pitch, roll, height, small shift of its floor point) fitted to the
pinned markers, with the camera floor point from the survey (O for CAM 1, CAM2 for CAM 2) and soft priors.
7 unknowns instead of a free 8-unknown homography, so 4-5 markers give real residuals and no wild fits.
Outputs: floor_cam1.json, floor_cam2.json   H = 3x3 homography, image pixel -> floor metres (origin O)
         floor_cam1_check.png, floor_cam2_check.png   0.5 m floor grid + surveyed points drawn on the photo
         floor_topdown.png   both photos warped onto the floor seen from above, with the surveyed points
A good fit: the grid lines run along the floor and wall base, every surveyed point sits on its spot.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
DATA, FIGURES = HERE / "data", HERE / "figures"
CAMS = ("cam1", "cam2")
PX_PER_M = 100                       # top-down picture scale
BOX = (-0.5, 9.0, -1.0, 5.0)         # top-down picture extent: x0, x1, y0, y1 (metres)
PIN_SIGMA = 3.0                      # assumed pin error, pixels
CAM_POINT = {"cam1": ("O", 0.05), "cam2": ("CAM2", 0.15)}   # camera floor point and its uncertainty (m)
HEIGHT_KEY = {"cam1": "cam_1", "cam2": "cam_2"}
# Cameras that see a coloured wall base: it is found automatically and every point on it must map to
# x = x_wall (corridor face). CAM 1 sees the yellow corridor wall; CAM 2's room wall is white (no clue).
WALL_BASE = {"cam1": "P0"}
WALL_SIGMA = 0.05                    # metres, for the wall line as a whole (spread over its points)


def wall_base_pixels(img, x_max):
    """Where saturated (yellow) wall meets the paler floor, one point per 10 px column, kept only
    if it lies on one straight image line (markers and people in front are dropped)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(float)
    h = img.shape[0]
    pts = []
    for x in range(5, min(x_max, img.shape[1] - 5), 10):
        S = hsv[:, x - 2:x + 3, 1].mean(1)
        for y in range(h // 2, h - 4):
            if S[y - 4:y].mean() > 160 and S[y + 1:y + 5].mean() < 145:
                pts.append((x, y))
                break
    pts = np.float64(pts)
    if len(pts) < 4:
        return np.zeros((0, 2))
    best = np.zeros(len(pts), bool)          # RANSAC over all point pairs: the line most points agree on
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            (x1, y1), (x2, y2) = pts[i], pts[j]
            a = (y2 - y1) / (x2 - x1)
            keep = np.abs(pts[:, 1] - (y1 + a * (pts[:, 0] - x1))) < 3
            if keep.sum() > best.sum():
                best = keep
    if best.sum() < 4:
        return np.zeros((0, 2))
    a, b = np.polyfit(pts[best, 0], pts[best, 1], 1)
    keep = np.abs(pts[:, 1] - (a * pts[:, 0] + b)) < 3
    return pts[keep]


def to_floor(H, pts):
    return cv2.perspectiveTransform(np.float64(pts).reshape(1, -1, 2), H)[0]


def camera_axes(yaw, pitch, roll):
    """World: x, y on the floor (y towards the door), z DOWN into the floor (right-handed).
    Rows = camera right, down, forward."""
    fwd = np.array([np.cos(yaw), np.sin(yaw), 0.0])
    down = np.array([0.0, 0.0, 1.0])
    fwd, down = np.cos(pitch) * fwd + np.sin(pitch) * down, np.cos(pitch) * down - np.sin(pitch) * fwd
    right = np.cross(down, fwd)
    right, down = np.cos(roll) * right + np.sin(roll) * down, np.cos(roll) * down - np.sin(roll) * right
    return np.array([right, down, fwd])


def project(p, xy, base, size):
    f, yaw, pitch, roll, h, dx, dy = p
    R = camera_axes(yaw, pitch, roll)
    C = np.array([base[0] + dx, base[1] + dy, -h])
    Xc = (np.c_[xy, np.zeros(len(xy))] - C) @ R.T
    return np.c_[f * Xc[:, 0] / Xc[:, 2] + size[0] / 2, f * Xc[:, 1] / Xc[:, 2] + size[1] / 2], Xc[:, 2]


def floor_homography(p, base, size):
    """Pixel -> floor (z = 0) homography of the fitted camera, sign fixed so w > 0 below the horizon."""
    f, yaw, pitch, roll, h, dx, dy = p
    R = camera_axes(yaw, pitch, roll)
    t = -R @ np.array([base[0] + dx, base[1] + dy, -h])
    K = np.array([[f, 0, size[0] / 2], [0, f, size[1] / 2], [0, 0, 1]])
    H = np.linalg.inv(K @ np.c_[R[:, 0], R[:, 1], t])
    return H if H[2] @ [size[0] / 2, size[1], 1] > 0 else -H


def solve_camera(src, dst, base, size, base_sigma, h_prior, wall=None, wall_x=None):
    h0, hs = (h_prior, 0.03) if h_prior else (0.8, 0.4)
    c = dst.mean(0)
    yaw0 = np.arctan2(c[1] - base[1], c[0] - base[0])
    n_wall = 0 if wall is None else len(wall)

    def res(p):
        uv, z = project(p, dst, base, size)
        r = np.where(np.repeat(z, 2) > 0.1, ((uv - src) / PIN_SIGMA).ravel(), 1e3)   # markers in front
        rw = []
        if n_wall:
            fx = to_floor(floor_homography(p, base, size), wall)[:, 0]
            rw = (fx - wall_x) / (WALL_SIGMA * np.sqrt(n_wall))
        return np.r_[r, rw, (p[0] - 800) / 300, p[3] / 0.1, (p[4] - h0) / hs,
                     p[5] / base_sigma, p[6] / base_sigma]

    best = None
    for pitch0 in (0.05, 0.15, 0.3):
        for dyaw in (-0.3, 0.0, 0.3):
            r = least_squares(res, [800, yaw0 + dyaw, pitch0, 0, h0, 0, 0])
            if best is None or r.cost < best.cost:
                best = r
    return best.x


def fit(cam, floor, heights):
    pins = json.loads((DATA / f"pins_{cam}.json").read_text(encoding="utf-8"))
    names = [k for k in pins["points"] if k in floor]
    src = np.float64([pins["points"][k] for k in names])
    dst = np.float64([floor[k] for k in names])
    size = pins["size"]
    key, base_sigma = CAM_POINT[cam]
    base = floor[key]
    h_prior = heights.get(HEIGHT_KEY[cam])
    wall, wall_x = None, None
    if cam in WALL_BASE:
        wall_x = floor[WALL_BASE[cam]][0]
        # only the wall left of the door (markers stand in the doorway, to the right of it)
        door_px = min(u for k, (u, v) in pins["points"].items() if k in ("M3", "M7"))
        wall = wall_base_pixels(cv2.imread(str(DATA / pins["image"])), int(door_px) - 15)
    p = solve_camera(src, dst, base, size, base_sigma, h_prior, wall, wall_x)
    H = floor_homography(p, base, size)
    px = np.linalg.norm(project(p, dst, base, size)[0] - src, axis=1)
    cm = np.linalg.norm(to_floor(H, src) - dst, axis=1)
    loo = {}                                     # leave one out: predict each marker from the others
    for i, k in enumerate(names):
        keep = np.arange(len(names)) != i
        pk = solve_camera(src[keep], dst[keep], base, size, base_sigma, h_prior, wall, wall_x)
        loo[k] = float(np.linalg.norm(to_floor(floor_homography(pk, base, size), src[i:i + 1])[0] - dst[i]))
    f, yaw, pitch, roll, h, dx, dy = p
    print(f"\n{cam}: {pins['image']}, {len(names)} markers {names}")
    print(f"  camera: focal {f:.0f} px, height {h:.2f} m, tilt down {np.degrees(pitch):.1f} deg, "
          f"roll {np.degrees(roll):.1f} deg, floor point moved {np.hypot(dx, dy) * 100:.0f} cm from {key}")
    if wall is not None and len(wall):
        off = (to_floor(H, wall)[:, 0] - wall_x) * 100
        print(f"  wall base: {len(wall)} points found on the photo, off the measured wall by "
              f"{np.median(off):+.0f} cm (median), {off.min():+.0f} .. {off.max():+.0f} cm")
    for i, k in enumerate(names):
        flag = "   <- re-pin this marker?" if px[i] > 3 * PIN_SIGMA else ""
        print(f"  {k:6s} off by {px[i]:5.1f} px = {cm[i] * 100:5.1f} cm   left out: {loo[k] * 100:5.1f} cm{flag}")
    out = {"_note": "generated by fit_floor.py; H maps image pixels to floor metres, origin O = floor under CAM 1",
           "image": pins["image"], "size": size, "names": names,
           "image_points": src.tolist(), "floor_points": dst.tolist(), "H": H.tolist(),
           "camera": {"focal_px": f, "yaw_deg": float(np.degrees(yaw)), "pitch_deg": float(np.degrees(pitch)),
                      "roll_deg": float(np.degrees(roll)), "height_m": h,
                      "floor_xy_m": [base[0] + dx, base[1] + dy]},
           "residual_px": dict(zip(names, px.round(2).tolist())),
           "residual_m": dict(zip(names, cm.round(4).tolist())), "leave_one_out_m": loo}
    (DATA / f"floor_{cam}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return H, pins["image"]


def draw_check(cam, H, image, floor):
    """0.5 m grid and surveyed points, projected from the floor back onto the photo."""
    img = cv2.imread(str(DATA / image))
    h, w = img.shape[:2]
    Hi = np.linalg.inv(H)

    def on_photo(p):
        q = Hi @ [p[0], p[1], 1]
        if abs(q[2]) < 1e-12:
            return None
        u, v = q[0] / q[2], q[1] / q[2]
        if H[2] @ [u, v, 1] <= 0:            # the spot is behind the camera
            return None
        return (int(u), int(v)) if -w < u < 2 * w and -h < v < 2 * h else None

    x0, x1, y0, y1 = BOX
    for v in np.arange(np.ceil(x0 * 2) / 2, x1 + 0.01, 0.5):
        for a, b in zip(np.arange(y0, y1, 0.1), np.arange(y0 + 0.1, y1 + 0.1, 0.1)):
            p, q = on_photo((v, a)), on_photo((v, b))
            if p and q:
                cv2.line(img, p, q, (0, 200, 255) if v % 1 == 0 else (0, 120, 160), 1, cv2.LINE_AA)
    for v in np.arange(np.ceil(y0 * 2) / 2, y1 + 0.01, 0.5):
        for a, b in zip(np.arange(x0, x1, 0.1), np.arange(x0 + 0.1, x1 + 0.1, 0.1)):
            p, q = on_photo((a, v)), on_photo((b, v))
            if p and q:
                cv2.line(img, p, q, (255, 160, 0) if v % 1 == 0 else (160, 100, 0), 1, cv2.LINE_AA)
    for k, xy in floor.items():
        p = on_photo(xy)
        if p and 0 <= p[0] < w and 0 <= p[1] < h:
            cv2.circle(img, p, 4, (0, 0, 255), -1)
            cv2.putText(img, k, (p[0] + 5, p[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)
    cv2.putText(img, f"{cam}: orange = x lines, blue = y lines (bright every 1 m); red = surveyed points",
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(str(FIGURES / f"floor_{cam}_check.png"), img)


def draw_topdown(fits, floor):
    x0, x1, y0, y1 = BOX
    W, Hh = int((x1 - x0) * PX_PER_M), int((y1 - y0) * PX_PER_M)
    # floor metres -> top-down pixels (x to the right, y down = towards the door)
    M = np.array([[PX_PER_M, 0, -x0 * PX_PER_M], [0, PX_PER_M, -y0 * PX_PER_M], [0, 0, 1]])
    canvas = np.full((Hh, W, 3), 255, np.uint8)
    for cam, (H, image) in fits.items():
        img = cv2.imread(str(DATA / image))
        ih, iw = img.shape[:2]
        uu, vv = np.meshgrid(np.arange(iw), np.arange(ih))
        wgt = H[2, 0] * uu + H[2, 1] * vv + H[2, 2]
        cam_xy = json.loads((DATA / f"floor_{cam}.json").read_text(encoding="utf-8"))["camera"]["floor_xy_m"]
        with np.errstate(divide="ignore", invalid="ignore"):
            fx = (H[0, 0] * uu + H[0, 1] * vv + H[0, 2]) / wgt
            fy = (H[1, 0] * uu + H[1, 1] * vv + H[1, 2]) / wgt
        # floor below the horizon only, and not too far (walls and furniture smear badly there)
        src_mask = ((wgt > 0) & (np.hypot(fx - cam_xy[0], fy - cam_xy[1]) < 6.0)).astype(np.uint8) * 255
        warp = cv2.warpPerspective(img, M @ H, (W, Hh))
        mask = cv2.warpPerspective(src_mask, M @ H, (W, Hh), flags=cv2.INTER_NEAREST)
        canvas[mask > 0] = (canvas[mask > 0] * 0.4 + warp[mask > 0] * 0.6).astype(np.uint8)
    P = lambda p: (int((p[0] - x0) * PX_PER_M), int((p[1] - y0) * PX_PER_M))
    for v in range(int(np.ceil(x0)), int(x1) + 1):
        cv2.line(canvas, P((v, y0)), P((v, y1)), (200, 200, 200), 1)
        cv2.putText(canvas, f"x {v}", P((v + 0.03, y0 + 0.2)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
    for v in range(int(np.ceil(y0)), int(y1) + 1):
        cv2.line(canvas, P((x0, v)), P((x1, v)), (200, 200, 200), 1)
        cv2.putText(canvas, f"y {v}", P((x0 + 0.03, v - 0.03)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
    wall = [floor[k] for k in ("P0", "glass_top", "glass_bottom", "door_top", "door_bottom") if k in floor]
    if wall:
        xw = wall[0][0]
        cv2.line(canvas, P((xw, y0)), P((xw, y1)), (0, 0, 0), 2)
    for k, xy in floor.items():
        col = (0, 0, 255) if k.startswith("M") else (0, 140, 0) if k.startswith(("D", "CAM", "O")) else (200, 0, 200)
        if k.endswith("_in"):
            continue
        cv2.circle(canvas, P(xy), 5, col, -1)
        cv2.putText(canvas, k, (P(xy)[0] + 6, P(xy)[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
    cv2.putText(canvas, "top-down, 1 grid square = 1 m. Photos warped onto the floor: only FLOOR texture is meant to line up",
                (8, Hh - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.imwrite(str(FIGURES / "floor_topdown.png"), canvas)


def click(cam, floor):
    data = json.loads((DATA / f"floor_{cam}.json").read_text(encoding="utf-8"))
    H = np.array(data["H"])
    img = cv2.imread(str(DATA / data["image"]))
    state = {"pt": None}
    marks = {k: v for k, v in floor.items() if not k.endswith("_in")}

    def on_mouse(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            state["pt"] = (x, y)
            fx, fy = to_floor(H, [(x, y)])[0]
            near = min(marks, key=lambda k: np.hypot(marks[k][0] - fx, marks[k][1] - fy))
            d = np.hypot(marks[near][0] - fx, marks[near][1] - fy)
            print(f"pixel ({x}, {y}) -> x {fx:.2f} m  y {fy:.2f} m   from O {np.hypot(fx, fy):.2f} m"
                  f"   nearest {near} {d:.2f} m")
            state["text"] = f"x {fx:.2f}  y {fy:.2f}  |  O {np.hypot(fx, fy):.2f} m  |  {near} {d:.2f} m"

    win = f"click a floor spot ({cam}), q = quit"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, img.shape[1], img.shape[0])
    cv2.setMouseCallback(win, on_mouse)
    print("Click where something touches the floor. Compare with a tape from O or from the nearest marker.")
    while True:
        view = img.copy()
        if state["pt"]:
            cv2.drawMarker(view, state["pt"], (0, 0, 255), cv2.MARKER_CROSS, 16, 2)
            cv2.rectangle(view, (0, 0), (view.shape[1], 30), (0, 0, 0), -1)
            cv2.putText(view, state["text"], (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)
        cv2.imshow(win, view)
        key = cv2.waitKey(20) & 0xFF
        if key in (ord("q"), 27) or cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
            break
    cv2.destroyAllWindows()


def main():
    solved = DATA / "result_solved.json"
    if not solved.exists():
        sys.exit("run  python ml/aruco/survey.py  first")
    solved = json.loads(solved.read_text(encoding="utf-8"))
    floor, heights = solved["points"], solved.get("cam_heights") or {}
    if len(sys.argv) >= 3 and sys.argv[1] == "click":
        return click(sys.argv[2], floor)
    fits = {}
    for cam in CAMS:
        if not (DATA / f"pins_{cam}.json").exists():
            print(f"\n{cam}: no pins_{cam}.json, run  python ml/aruco/pin_points.py {cam}")
            continue
        fits[cam] = fit(cam, floor, heights)
        draw_check(cam, *fits[cam], floor)
    draw_topdown(fits, floor)
    print("\nWrote floor_cam*.json, floor_cam*_check.png, floor_topdown.png")


if __name__ == "__main__":
    main()
