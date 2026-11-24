"""Calibrate a floor homography by hand: click the same floor point in the camera frame and on the map.

    .venv/Scripts/python ml/tracking/calibrate_homography.py --cam cam_1
    .venv/Scripts/python ml/tracking/calibrate_homography.py --cam cam_2 --load      # start from the saved points
    .venv/Scripts/python ml/tracking/calibrate_homography.py --cam cam_1 --video data/videos/take1/cam_1.mp4 --at 5

Left: camera frame (data/calibration/<cam>_frame.png, or a frame of --video at --at seconds).
Right: Room 204 map (data/calibration/room204_map.png, the FigJam drawing, 920 x 520 = map fractions 0..1).

Mouse / keys
    left click on the frame, then on the map   add one point pair (the pair being added is yellow)
    right click                                 delete the nearest pair (frame or map side)
    f                                           fit (also done after every change once there are >= 4 pairs)
    g                                           toggle the floor grid projected onto the frame (checks the fit)
    s                                           save <cam>_homography.json (old file kept as .bak)
    q / Esc                                     quit (asks nothing: save first)

Only click points ON THE FLOOR (wall/door-frame feet, desk legs, tape marks), spread near/far and left/right.
8-15 pairs is good. The panel shows the error of every pair (map px) and its leave-one-out error: a pair with
a large leave-one-out error was probably clicked wrong.
"""
import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
CAL = REPO / "data" / "calibration"
MAP_W, MAP_H = 920, 520
WIN = "calibrate homography"


def load_frame(cam, video, at):
    if video:
        cap = cv2.VideoCapture(str(video))
        cap.set(cv2.CAP_PROP_POS_MSEC, at * 1000)
        ok, img = cap.read()
        cap.release()
        if not ok:
            raise SystemExit(f"cannot read {video} at {at} s")
    else:
        img = cv2.imread(str(CAL / f"{cam}_frame.png"))
        if img is None:
            raise SystemExit(f"missing {CAL / (cam + '_frame.png')}")
    return img


def fit(img_pts, map_pts):
    """H (image px -> map fraction), per-pair error and leave-one-out error, both in map px."""
    if len(img_pts) < 4:
        return None, [], []
    src, dst = np.float64(img_pts), np.float64(map_pts)
    H, _ = cv2.findHomography(src, dst, 0)
    if H is None:
        return None, [], []
    scale = np.array([MAP_W, MAP_H])

    def err(Hm, i):
        p = Hm @ np.array([*src[i], 1.0])
        return float(np.linalg.norm((p[:2] / p[2] - dst[i]) * scale))

    errs = [err(H, i) for i in range(len(src))]
    loo = []
    for i in range(len(src)):
        keep = [j for j in range(len(src)) if j != i]
        Hi = cv2.findHomography(src[keep], dst[keep], 0)[0] if len(keep) >= 4 else None
        loo.append(err(Hi, i) if Hi is not None else float("nan"))
    return H, errs, loo


class App:
    def __init__(self, cam, frame, map_img, pts):
        self.cam, self.frame, self.map = cam, frame, map_img
        self.fh, self.fw = frame.shape[:2]
        self.pairs = pts                      # [[(u, v), (mx, my) or None], ...]
        self.grid = True
        self.H, self.errs, self.loo = None, [], []
        self.refit()

    # map side drawn to the right of the frame, top aligned
    def to_canvas_map(self, mx, my):
        return int(self.fw + mx * MAP_W), int(my * MAP_H)

    def refit(self):
        done = [p for p in self.pairs if p[1] is not None]
        self.H, self.errs, self.loo = fit([p[0] for p in done], [p[1] for p in done])

    def on_mouse(self, ev, x, y, flags, _):
        on_map = x >= self.fw and y < MAP_H
        if ev == cv2.EVENT_LBUTTONDOWN:
            pending = self.pairs and self.pairs[-1][1] is None
            if not on_map and x < self.fw and not pending:
                self.pairs.append([(float(x), float(y)), None])
            elif on_map and pending:
                self.pairs[-1][1] = ((x - self.fw) / MAP_W, y / MAP_H)
                self.refit()
        elif ev == cv2.EVENT_RBUTTONDOWN and self.pairs:
            def dist(p):
                if on_map:
                    return np.hypot(*(np.subtract(self.to_canvas_map(*p[1]), (x, y)))) if p[1] else 1e9
                return np.hypot(p[0][0] - x, p[0][1] - y)
            self.pairs.pop(int(np.argmin([dist(p) for p in self.pairs])))
            self.refit()

    def draw(self):
        h = max(self.fh, MAP_H + 260)
        canvas = np.full((h, self.fw + MAP_W, 3), 40, np.uint8)
        canvas[:self.fh, :self.fw] = self.frame
        canvas[:MAP_H, self.fw:] = self.map

        if self.grid and self.H is not None:
            Hinv = np.linalg.inv(self.H)
            # sign of w for map points in front of the camera = sign for a clicked (visible) floor point
            ref = next(p[1] for p in self.pairs if p[1] is not None)
            front = np.sign((Hinv @ np.array([*ref, 1.0]))[2])
            for k in np.linspace(0, 1, 21):
                for line in ([(k, t) for t in np.linspace(0, 1, 60)], [(t, k) for t in np.linspace(0, 1, 60)]):
                    pts = []
                    for mx, my in line:
                        p = Hinv @ np.array([mx, my, 1.0])
                        if p[2] * front > 0:   # in front of the camera
                            pts.append((p[0] / p[2], p[1] / p[2]))
                    pts = np.int32([q for q in pts if -2000 < q[0] < 4000 and -2000 < q[1] < 4000])
                    if len(pts) > 1:
                        cv2.polylines(canvas[:self.fh, :self.fw], [pts], False, (0, 200, 255), 1, cv2.LINE_AA)

        for i, (ip, mp) in enumerate(self.pairs):
            col = (0, 255, 255) if mp is None else (60, 220, 60)
            if mp is not None and i < len(self.loo) and self.loo[i] == self.loo[i] and self.loo[i] > 25:
                col = (60, 60, 255)
            cv2.circle(canvas, (int(ip[0]), int(ip[1])), 6, col, 2)
            cv2.putText(canvas, str(i + 1), (int(ip[0]) + 8, int(ip[1]) - 8), 0, 0.6, col, 2)
            if mp is not None:
                c = self.to_canvas_map(*mp)
                cv2.circle(canvas, c, 6, col, 2)
                cv2.putText(canvas, str(i + 1), (c[0] + 8, c[1] - 8), 0, 0.6, col, 2)
                if self.H is not None:   # where the fit puts this frame point on the map
                    p = self.H @ np.array([*ip, 1.0])
                    q = self.to_canvas_map(p[0] / p[2], p[1] / p[2])
                    cv2.line(canvas, c, q, (255, 0, 255), 1)
                    cv2.drawMarker(canvas, q, (255, 0, 255), cv2.MARKER_CROSS, 10, 1)

        y = MAP_H + 24
        x0 = self.fw + 10
        pending = self.pairs and self.pairs[-1][1] is None
        msg = "now click the SAME point on the map" if pending else "click a floor point on the camera frame"
        cv2.putText(canvas, f"{self.cam}: {msg}", (x0, y), 0, 0.55, (255, 255, 255), 1)
        y += 24
        if self.H is None:
            cv2.putText(canvas, "need >= 4 pairs to fit", (x0, y), 0, 0.55, (200, 200, 200), 1)
        else:
            loo = f"{np.nanmean(self.loo):.1f} px" if len(self.loo) > 4 else "n/a (need >= 5 pairs)"
            cv2.putText(canvas, f"mean err {np.mean(self.errs):.1f} px   mean leave-one-out {loo}",
                        (x0, y), 0, 0.55, (255, 255, 255), 1)
            for i, (e, l) in enumerate(zip(self.errs, self.loo)):
                y += 20
                if y > h - 30:
                    break
                bad = l == l and l > 25
                cv2.putText(canvas, f"{i + 1:2d}: err {e:5.1f}  loo {l:6.1f}{'  <- check' if bad else ''}",
                            (x0, y), 0, 0.5, (100, 100, 255) if bad else (220, 220, 220), 1)
        cv2.putText(canvas, "f fit  g grid  right-click delete  s save  q quit", (x0, h - 10), 0, 0.5,
                    (180, 180, 180), 1)
        return canvas

    def save(self, source):
        if self.H is None:
            print("not saved: need >= 4 pairs")
            return
        path = CAL / f"{self.cam}_homography.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if path.is_file():
            shutil.copy(path, path.with_suffix(".json.bak"))
        done = [p for p in self.pairs if p[1] is not None]
        old.update({
            "cam_id": self.cam,
            "frame_size": [self.fw, self.fh],
            "image_points": [[round(u, 1), round(v, 1)] for (u, v), _ in done],
            "map_points": [[round(x, 4), round(y, 4)] for _, (x, y) in done],
            "H": (self.H / self.H[2, 2]).tolist(),
            "method": f"hand calibration, calibrate_homography.py ({len(done)} floor points, frame: {source})",
            "mean_error_map_px": round(float(np.mean(self.errs)), 2),
            "mean_loo_error_map_px": round(float(np.nanmean(self.loo)), 2),
        })
        path.write_text(json.dumps(old, indent=1) + "\n", encoding="utf-8")
        print(f"saved {path} (old file: {path.with_suffix('.json.bak').name})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cam", required=True, choices=["cam_1", "cam_2"])
    ap.add_argument("--video", help="take a frame from this video instead of <cam>_frame.png")
    ap.add_argument("--at", type=float, default=0.0, help="seconds into --video")
    ap.add_argument("--load", action="store_true", help="start from the points in <cam>_homography.json")
    a = ap.parse_args()

    frame = load_frame(a.cam, a.video, a.at)
    map_img = cv2.imread(str(CAL / "room204_map.png"))
    if map_img is None:
        raise SystemExit(f"missing {CAL / 'room204_map.png'}")
    map_img = cv2.resize(map_img, (MAP_W, MAP_H))

    pts = []
    if a.load:
        saved = json.loads((CAL / f"{a.cam}_homography.json").read_text(encoding="utf-8"))
        pts = [[tuple(i), tuple(m)] for i, m in zip(saved["image_points"], saved["map_points"])]

    app = App(a.cam, frame, map_img, pts)
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 1600, 640)
    cv2.setMouseCallback(WIN, app.on_mouse)
    while True:
        cv2.imshow(WIN, app.draw())
        k = cv2.waitKey(30) & 0xFF
        if k in (ord("q"), 27) or cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:
            break
        if k == ord("f"):
            app.refit()
        elif k == ord("g"):
            app.grid = not app.grid
        elif k == ord("s"):
            app.save(a.video and f"{a.video} @ {a.at}s" or f"{a.cam}_frame.png")
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
