# Presence verification — work in progress (Đức Mạnh)

Only for the presence verification + door audit module and the floor-map calibration it depends on.
Design and results: `ml/presence_verification/README.md`, `PLAN.md` (Vietnamese), `TEST.md`. This file is the
running state: what changed lately, what is open, what to do next. Update it when you finish a step.

Last updated: 2026-11-24.

## The module in short

- **Door audit:** pairs every check-in with a door entry (Hungarian assignment, logistic-regression pair cost).
  Alerts D1 (entered without check-in), D2 (tailgating), D3 (checked in, never entered).
- **Presence:** per-student features from the map trajectory → rules R1–R5 + a model score (RandomForest selected
  by val AUC). Trained on simulated sessions (`simulate.py`), evaluated on simulated test + the 8 recorded takes.
- **Served by** `backend/app/features/presence_verification/` (`/take/{n}`, `/model`, `/live`). Live mode is a TODO.
- **Shown in** the Demo page: `PresencePanel.vue` and trails on `RoomMap.vue`.

## Floor map and calibration (source of truth)

| What | Where |
| --- | --- |
| Room 204 drawing | FigJam board `b8wiU877MrltPtUYAI4BiW`, section "Room 204 map" (node 19:6). Second section "Room 204 map of take 1 where Chi sits" (24:152) marks Chi's seat in take 1 at map (0.556, 0.698) |
| Map geometry for the ML code | `data/calibration/room204_map.json` (fractions 0–1 of the 920×520 drawing; door gap y 0.727–0.906, same as Figma) |
| Map drawing for the web | `frontend/src/roomLayout.js` (Figma px; 8 long tables 198×36, cameras at their Figma positions) |
| Map image for the click tool | `data/calibration/room204_map.png` (crop of the Figma drawing) |
| Homographies (image px → map fraction) | `data/calibration/cam_1_homography.json`, `cam_2_homography.json` |
| Hand-calibration tool | `ml/tracking/calibrate_homography.py` (click floor point on frame, then on map; `g` grid, `s` save, `--load`, `--video`) |

The map scale (`scale_per_m` x 0.0875, y 0.143) is an assumption, never measured. Figma desks are approximate.

## Calibration done on 2026-11-24

The old homographies (`ground_model.py`, 4 points all at the bottom of the frame) put people through walls.
Both cameras were refitted with a pinhole camera model (focal, position, height, yaw, pitch) on floor clues,
then saved as point pairs + H in the usual JSON format (scripts were in the session scratchpad, not in the repo).

- **cam_1:** wall base (HSV mask), both door-jamb feet, end of the yellow wall, base of the open door leaf.
  f 752 px, height 0.73 m, facing south-east, residuals ≤ 6 px. Check: leaf length came out 1.08 m (Figma 1.11 m).
  All cam_1 tracks now stay corridor → door (takes 1, 3, 4, 8).
- **cam_2:** door jambs, door leaf, back/south wall base + the two near-end legs of Chi's table (Figma row 4 col 1)
  as image-column constraints (feet below the frame). Focal fixed near cam_1's (otherwise degenerate).
  f 760 px, height 0.83 m, at map (0.755, 0.795). Cost: north jamb ~26 px off, leaf ~14–20 px (Figma tables and door
  do not fully agree). A free map aspect gave a non-physical room (4.1 m deep) and was rejected.
- Backups: `cam_1_homography.json.bak` / `cam_2_homography.json.bak` = original estimates;
  `cam_2_homography.v1.json.bak`, `.v2.json.bak` = earlier cam_2 hand fits. Not committed.
- `simulate.py`: `DOOR_IN` moved to the new door centre (0.33, 0.8165).

## Open problems

1. **Chi (take 1) is ~0.06 north of her Figma seat** (trail ends (0.533, 0.636), seat (0.556, 0.698)). She is seated
   and her box is cut by the frame bottom, so the "feet" point is her knees. Homography alone cannot fix it.
   Options: a rule for cut/seated boxes (head top + seated height prior, or pose keypoints), or more floor markers.
   Head + 1.25 m prior gave (0.593, 0.644), not better. Waiting for the user's choice.
2. **Model not retrained** after the new homographies and door gap: run `train.py` then `evaluate.py`, compare with
   the README numbers.
3. **Figma vs real room:** desks, south wall segment (cam_2 fit suggests y ≈ 0.93–0.95, Figma 1.0) and the metre
   scale are unmeasured. Only measured floor markers (see PLAN / the plan below) can settle it.
4. Camera movement between takes not yet checked (open other takes with `calibrate_homography.py --load --video`).
5. Figma write access: `use_figma` was denied by the permission classifier; Figma edits are done by the user.

## Plan for better map accuracy (agreed direction, not built)

0. Ground truth: tape 10–15 floor markers, measure them in metres, film a person on each.
1. Refit homographies from the markers (+ undistortion), map in metres.
2. Feet from pose keypoints (ankles); head + height prior when the feet are hidden.
3. Optional: small model on the residual error.
4. Kalman filter per person, fuse cam_1 + cam_2 at the door, keep points inside the map.

## How to check

```bash
.venv/Scripts/python ml/tracking/calibrate_homography.py --cam cam_2 --load        # g = floor grid on the frame
.venv/Scripts/python ml/presence_verification/trajectories.py --take 1 --plot
.venv/Scripts/python -m unittest discover -s ml/presence_verification/tests       # 19 tests
```
Video of a take: `python -c "import sys;sys.path.insert(0,'ml/tracking');from paths import video_path;print(video_path('cam_2',1))"`
(`.webm` reports 1000 fps: use `--at 0`, or count frames at ~30 fps).
