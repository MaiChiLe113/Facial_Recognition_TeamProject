"""Put the measured room and camera fits into the app: room204_map.json + the per-camera homographies.

  python ml/aruco/apply_calibration.py

Reads  data/result_solved.json (survey.py), data/floor_cam1.json / floor_cam2.json (fit_floor.py)
Writes data/calibration/room204_map.json          walls, door, glass, desk D7 (+ the other desks moved with it), cameras
       data/calibration/cam_N_homography_live.json  pixel -> map for the CURRENT camera pose (live mode)
       data/calibration/cam_N_homography.json       pixel -> map for the pose of the recorded takes
                                                    (cam_N_frame.png): the live fit carried over by registering
                                                    that frame onto today's photo (valid if the camera only turned)
Old files are kept as .bak (once; an existing .bak is not overwritten).

Metres (origin O = floor under CAM 1, x -> room, y -> door) become map fractions with the map's
scale_per_m; the wall centre sits on corridor_wall_x and the door centre stays where the map had it.
"""
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
REPO = HERE.parents[1]
CAL = REPO / "data" / "calibration"
CAMS = {"cam1": "cam_1", "cam2": "cam_2"}
DESK_D7 = 6               # index of desk D7 (row 4, column 1) in room204_map.json "desks"
LONG_DESKS = range(8)     # the 8 long desks; the last entry (small desk by CAM 2) is not measured


def backup(path):
    bak = path.with_name(path.name + ".bak")
    if path.exists() and not bak.exists():
        shutil.copy2(path, bak)


def metres_to_map(mp, pts):
    xw = pts["P0"][0] + (pts["P0_in"][0] - pts["P0"][0]) / 2          # centre of the wall
    door_c = (pts["door_top"][1] + pts["door_bottom"][1]) / 2
    sx, sy = mp["scale_per_m"]["x"], mp["scale_per_m"]["y"]
    x0 = mp["corridor_wall_x"] - xw * sx
    y0 = mp["door"]["centre"][1] - door_c * sy
    return np.array([[sx, 0, x0], [0, sy, y0], [0, 0, 1.0]])


def apply(A, xy):
    return [round(float(v), 4) for v in cv2.perspectiveTransform(np.float64([[xy]]), A)[0, 0]]


def register(src_img, dst_img):
    """Image homography src -> dst from the static background (SIFT + RANSAC)."""
    cl = cv2.createCLAHE(2.0, (8, 8))
    g = lambda i: cl.apply(cv2.cvtColor(i, cv2.COLOR_BGR2GRAY))
    sift = cv2.SIFT_create(12000, contrastThreshold=0.01)
    ka, da = sift.detectAndCompute(g(src_img), None)
    kb, db = sift.detectAndCompute(g(dst_img), None)
    m = [a for a, b in cv2.BFMatcher().knnMatch(da, db, k=2) if a.distance < 0.75 * b.distance]
    A = np.float32([ka[x.queryIdx].pt for x in m])
    B = np.float32([kb[x.trainIdx].pt for x in m])
    T, inl = cv2.findHomography(A, B, cv2.RANSAC, 3.0)
    inl = inl.ravel().astype(bool)
    err = np.linalg.norm(cv2.perspectiveTransform(A[None], T)[0] - B, axis=1)[inl]
    return T, int(inl.sum()), float(np.median(err))


def homography_file(cam_id, H, img_pts, map_pts, method, frame):
    """map_points = where H puts image_points (consistent pairs, as calibrate_homography.py expects);
    survey_map_points = where the tape survey puts those markers; the gap is the fit error."""
    H = H / H[2, 2]
    proj = cv2.perspectiveTransform(np.float64([img_pts]), H)[0]
    err_px = float(np.mean(np.linalg.norm((proj - np.float64(map_pts)) * [920, 520], axis=1)))
    return {"cam_id": cam_id, "frame_size": [1280, 720], "frame": frame,
            "image_points": [[round(float(u), 1), round(float(v), 1)] for u, v in img_pts],
            "map_points": [[round(float(x), 4), round(float(y), 4)] for x, y in proj],
            "survey_map_points": map_pts, "H": H.tolist(), "method": method,
            "mean_error_map_px": round(err_px, 2)}


def main():
    solved = json.loads((DATA / "result_solved.json").read_text(encoding="utf-8"))
    pts = solved["points"]
    path = CAL / "room204_map.json"
    mp = json.loads(path.read_text(encoding="utf-8"))
    A = metres_to_map(mp, pts)
    M = lambda k: apply(A, pts[k])

    # ---- room204_map.json
    backup(path)
    mp["_note"] = ("Top-down model of the corridor + Room 204. Coordinates are fractions of the map: x 0 left -> 1 right, "
                   "y 0 top -> 1 bottom, same convention as RoomMap.vue. Wall, door, glass, desk D7 and both cameras "
                   "come from the tape survey of 2026-11-25 (result.yaml -> survey.py -> apply_calibration.py); "
                   "the map outline and the other desks' spacing are still not measured.")
    mp["door"]["y"] = [M("door_top")[1], M("door_bottom")[1]]
    mp["door"]["centre"] = [mp["corridor_wall_x"], round(sum(mp["door"]["y"]) / 2, 4)]
    mp["door"]["_note"] = "measured (door_top / door_bottom of result.yaml)"
    mp["glass_window"]["y"] = [M("glass_top")[1], M("glass_bottom")[1]]
    mp["glass_window"]["_note"] = "measured (glass_top / glass_bottom of result.yaml)"
    if solved.get("desks_xywh", {}).get("D7"):
        x, y, L, W = solved["desks_xywh"]["D7"]
        nx, ny = apply(A, (x, y))
        w, h = round(L * A[0, 0], 4), round(W * A[1, 1], 4)
        old = mp["desks"][DESK_D7][:2]
        dx, dy = nx - old[0], ny - old[1]
        for i in LONG_DESKS:
            ox, oy = mp["desks"][i][:2]
            mp["desks"][i] = [round(ox + dx, 4), round(oy + dy, 4), w, h]
        att = mp["cameras"].get("attendance_cam")
        if att:
            att["x"], att["y"] = round(att["x"] + dx, 4), round(att["y"] + dy, 4)
            att["_note"] = "on desk D7 (moved with the desks to the measured D7 on 2026-11-25)"
        mp["_desks_note"] = ("[x, y, w, h] fractions, top-left corner. Size = measured desk_L x desk_W. D7 (index 6) is "
                             "measured; the other long desks keep their old spacing, moved with D7. Last entry = small desk "
                             "by CAM 2, not measured.")
    fits = {cam: json.loads((DATA / f"floor_{cam}.json").read_text(encoding="utf-8")) for cam in CAMS}
    for cam, cam_id in CAMS.items():
        c = fits[cam]["camera"]
        mx, my = apply(A, c["floor_xy_m"])
        mp["cameras"][cam_id].update(x=mx, y=my, _note=(
            f"fitted on {fits[cam]['image']} (fit_floor.py, 2026-11-25): {c['height_m']:.2f} m high, "
            f"focal {c['focal_px']:.0f} px"))
    path.write_text(json.dumps(mp, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}: door y {mp['door']['y']}, glass y {mp['glass_window']['y']}")

    # ---- homographies
    for cam, cam_id in CAMS.items():
        f = fits[cam]
        H_live = A @ np.array(f["H"])                         # today's pixel -> map
        img_pts, map_pts = f["image_points"], [apply(A, p) for p in f["floor_points"]]
        live = CAL / f"{cam_id}_homography_live.json"
        live.write_text(json.dumps(homography_file(
            cam_id, H_live, img_pts, map_pts,
            f"fit_floor.py camera model on {f['image']} (pins + survey), converted to map fractions", f["image"]),
            indent=1), encoding="utf-8")
        print(f"wrote {live.relative_to(REPO)}")

        frame = CAL / f"{cam_id}_frame.png"
        T, n, med = register(cv2.imread(str(frame)), cv2.imread(str(DATA / f["image"])))   # old frame -> photo
        H_rec = H_live @ T
        rec_pts = cv2.perspectiveTransform(np.float64([img_pts]), np.linalg.inv(T))[0].tolist()
        rec = CAL / f"{cam_id}_homography.json"
        backup(rec)
        rec.write_text(json.dumps(homography_file(
            cam_id, H_rec, rec_pts, map_pts,
            f"live fit carried to {frame.name} by image registration ({n} background matches, median {med:.2f} px)",
            frame.name), indent=1), encoding="utf-8")
        shift = np.linalg.norm(cv2.perspectiveTransform(np.float64([[(640, 600)]]), T)[0, 0] - (640, 600))
        print(f"wrote {rec.relative_to(REPO)}  (recorded frame vs today's photo: {shift:.0f} px apart at the floor, "
              f"{n} matches, median {med:.2f} px)")


if __name__ == "__main__":
    main()
