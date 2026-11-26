# ArUco floor calibration (Đức Mạnh)

Maps a pixel on `cam_1` / `cam_2` to a position on the Room 204 floor map, using printed ArUco markers (DICT_4X4_50) at
tape-measured positions. It replaces the hand-clicked homographies, which were fitted to an unmeasured map.

## Method

1. **Survey** (`survey.py`): only straight tape distances between points are measured ([MEASURING.md](MEASURING.md)). All
   floor positions are solved together by least squares (trilateration), which also reports each point's uncertainty and
   any distance that disagrees.
2. **Pins** (`pin_points.py`): the floor pixel of each marker. Markers OpenCV reads are automatic (three detector passes,
   see `check_aruco.py`); for a standing sheet the bottom edge of the paper is extrapolated and snapped to the paper/floor
   edge. Unread markers are clicked by hand.
3. **Camera fit** (`fit_floor.py`): a pinhole camera (focal, yaw, pitch, roll, height, small floor-point shift) is fitted
   to the pins with soft priors, plus the yellow wall base on CAM 1. It has 7 unknowns instead of the 8 of a free
   homography, so 4–5 markers still leave real residuals.
4. **Apply** (`apply_calibration.py`): writes the measured geometry and the homographies into `data/calibration/`. The
   cameras had moved since the recorded takes, so each camera gets two files: `cam_N_homography_live.json` (pose on the
   survey day, used by live mode) and `cam_N_homography.json` (pose of the recorded takes, carried over by registering
   the static background with SIFT + RANSAC, which assumes the camera only turned).

## Results (survey of 2026-11-25)

Survey: no tape distance is off by more than the 3 cm flag. `CAM2` (±15 cm) and `M2` (±7 cm) are flagged as uncertain.

| Camera | Markers | Fit error per marker | Leave-one-out error | Fitted height | Recorded vs survey-day pose |
| --- | --- | --- | --- | --- | --- |
| cam_1 | 3–7 (5) | 0.3–6.2 cm | 2.1–8.7 cm | 0.88 m | 53 px at the floor |
| cam_2 | 0, 2, 3, 7 (4) | 0.8–11.9 cm | 19.7–59.8 cm | 1.03 m | 39 px at the floor |

Leave-one-out predicts each marker from a fit without it, so it is the better estimate of real accuracy.

Figures:

- `figures/plan_A.png` … `plan_D.png`: the measuring plan (planned positions, drawn before the survey)
- `figures/floor_cam1_check.png`, `floor_cam2_check.png`: 0.5 m floor grid and surveyed points on the camera photos
- `figures/floor_topdown.png`: both photos warped onto the floor, seen from above

## Limits

- CAM 2 is weak away from the door: all its markers are near it, and none is spare.
- `data/cam2_fixed.jpg` is a flipped, cropped screenshot, so its pixels only approximate the live frame.
- On the two saved photos `check_aruco.py` reports FAIL: M3 (CAM 1) and M2 (CAM 2) are not read and were pinned by hand.
- Desk D7 is the only measured desk (D1, D3, D5 were skipped); the other long desks moved with it. The map outline and the
  camera heights were not measured.
- No lens distortion model.

## Run

From the repo root (needs opencv, numpy, scipy, pyyaml, pillow). The saved inputs reproduce the committed calibration.

```bash
python ml/aruco/survey.py             # data/result.yaml -> data/result_solved.json
python ml/aruco/pin_points.py cam1    # data/cam1_fixed.jpg -> data/pins_cam1.json (saved clicks are reused)
python ml/aruco/pin_points.py cam2
python ml/aruco/fit_floor.py          # -> data/floor_cam*.json, figures/floor_*.png
python ml/aruco/apply_calibration.py  # -> data/calibration/ (the files the app and ml/presence_verification read)
```

`python ml/aruco/fit_floor.py click cam1` prints the floor position of a clicked pixel, to check against a tape.

**New survey or a moved camera:** save the new photos in `data/` (update the file names in `pin_points.py`), delete
`data/pins_cam*.json` so old clicks are not reused, then run the chain again.

**Changing the measuring steps:** edit `MEASURING.md`, mirror it in `data/result.yaml` (same key, same `# N.` step), add
a rough position for any new point to `GUESS` in `survey.py` and to `PTS` in `draw_plan.py`, then run `draw_plan.py`.
Never edit the plan pictures by hand (it uses the Windows Segoe UI font).
