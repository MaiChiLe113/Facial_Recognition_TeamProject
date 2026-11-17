# Tracking (Mai Chi)

Person detection + tracking for the three demo cameras. Output feeds the Home page through
`GET /api/tracks/{cam_id}` (see the root README, "Data contract for bounding boxes").

All commands run from the repo root.

Take numbering: the original take 1 was a failed recording and was deleted on 2026-11-17; the
other takes were renumbered 2→1 … 9→8 (the old demo take 4 is now take 3). Older commits use the old
numbers.

## 1. Environment

Python 3.10+ (this setup used 3.12) and FFmpeg.

```bash
brew install ffmpeg                       # ffmpeg + ffprobe, needed for inspection and conversion
python3.12 -m venv ml/.venv
ml/.venv/bin/pip install -r ml/tracking/requirements.txt
```

`ml/.venv/`, `runs/`, `data/raw/` and weight files (`*.pt`, …) are git-ignored.
`yolo11n.pt` is downloaded once to `ml/tracking/yolo11n.pt` on first use. On Apple Silicon the
scripts run on PyTorch MPS, else CPU.

## 2. Video paths

`paths.py` resolves a camera's recording the same way the backend does:

```
HAWKEYE_VIDEO_ROOT (backend/.env) / cameras[].folder / takes[].files[cam_id]   (data/video_config.json)
```

The take is `"take"` in `data/video_config.json` unless one is passed. If
`data/raw/converted/<cam_id>_take<N>.mp4` exists, `video_path()` returns that instead (section 3).

```bash
ml/.venv/bin/python ml/tracking/paths.py            # configured take
ml/.venv/bin/python ml/tracking/paths.py --take 7
```

If a file shows `exists=False` although it is on Google Drive, it is probably cloud-only:
right-click the folder in Finder → **Make available offline**.

## 3. Inspect and convert the videos

`notebooks/01_explore.ipynb` does this for the configured take. The browser `.webm` recordings
report 1000 fps, no duration and an invalid frame count, so the real timing is measured from packet
timestamps:

```bash
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 in.webm | tail -1   # real duration
ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 in.webm
```

and every file is converted to constant 30 fps MP4 (originals untouched):

```bash
ffmpeg -i in.webm -vf fps=30 -c:v libx264 -preset veryfast -crf 20 -an data/raw/converted/<cam_id>_take<N>.mp4
```

`fps=30` follows the real timestamps (drops/duplicates frames), so the true duration is kept.
The notebook then checks: fps = 30 (ffprobe and OpenCV), duration within 0.2 s of the real
duration, and the three cameras within 1 s of each other. All 8 takes are converted and pass
(largest spread between cameras: 0.37 s, take 3).

## 4. Precompute the demo tracks

```bash
for t in 1 2 3 4 5 6 7 8; do
  ml/.venv/bin/python ml/tracking/precompute_tracks.py --cam all --take $t \
      --tracker ml/tracking/configs/bytetrack_long.yaml
done
```

Writes `data/tracks/take<N>/{cam_1,cam_2,attendance_cam}.json` for every take (committed; the Home
and Demo pages draw them). Then name the people on the attendance camera (it rewrites the
`attendance_cam.json` files, so run it after every precompute):

```bash
ml/.venv/bin/python ml/face_recognition/name_tracks.py --take all
```

`name_tracks.py` names attendance-camera tracks from enrolment photos (see
`ml/face_recognition/README.md`) and then runs `link_names.py` (it can also be run on its own), which
carries each name to cam_1 and cam_2: the track whose
feet are at the classroom door (floor map, section 7) while the named person is on the attendance
camera gets the same name, from the check-in time on. It names only one track per camera and skips
ambiguous cases (two people at the door). Take 1: Mai Chi is named on cam_1 ID 5 and cam_2 ID 5 from
6.4 s; face matching run directly on cam_2 agrees (52 of 116 face crops of ID 5 match her, no other
cam_2 track matches more than once). Not covered yet: later tracks of the same person (after an
occlusion, or seen through the glass by cam_1) and one shared ID number across cameras; both need
the Re-ID matcher (Phase B).
Defaults: `yolo11n.pt` (pre-trained, not fine-tuned), class 0 (person), `--conf 0.4`,
keyframe every 3rd frame (`--every-n 3`), tracks with fewer than 5 keyframes dropped
(`--min-keyframes 5`), and static tracks dropped (a box that never moves or changes size over its whole
life, e.g. the poster of a man on the classroom wall that YOLO detects as a person; `--keep-static`
turns this off; thresholds and how they were measured are in `is_static()`). `t = frame_index / fps` of the processed file; `box = [x, y, w, h]` as
fractions of the frame with `x, y` the top-left corner. `global_id` is the camera-local ByteTrack
ID until cross-camera matching replaces it. `attendance_cam` uses the same person detector for now.

### Tracker choice (E1 baseline)

The committed `data/tracks/` files come from
**`configs/bytetrack_long.yaml`** plus the static filter. That config is Ultralytics' `bytetrack.yaml` with `track_buffer: 90` instead of
30, so a lost person is kept alive for ~3 s at 30 fps instead of ~1 s.

| take | cam_id | tracker | IDs before filtering | IDs kept | real people |
| --- | --- | --- | --- | --- | --- |
| 3 | cam_1 | bytetrack | 20 | 16 | 4 |
| 3 | cam_1 | bytetrack_long | 17 | 13 | 4 |
| 3 | cam_2 | bytetrack | 24 | 15 | 4 |
| 3 | cam_2 | bytetrack_long | 20 | 14 | 4 |
| 3 | attendance_cam | bytetrack | 5 | 4 | 3 |
| 3 | attendance_cam | bytetrack_long | 5 | 4 | 3 |
| 1 | cam_1 | bytetrack | 22 | 15 | 4 |
| 1 | cam_1 | bytetrack_long | 16 | 11 | 4 |
| 1 | cam_2 | bytetrack | 17 | 7 | 4 |
| 1 | cam_2 | bytetrack_long | 17 | 7 | 4 |
| 1 | attendance_cam | bytetrack | 4 | 4 | 4 |
| 1 | attendance_cam | bytetrack_long | 4 | 4 | 4 |

With the static filter (`+static_filter`, now the default) only the poster tracks are removed:

| take | cam_id | tracker | IDs kept | real people | static tracks removed |
| --- | --- | --- | --- | --- | --- |
| 3 | cam_1 | bytetrack | 14 | 4 | 2 (poster, split in two) |
| 3 | cam_1 | bytetrack_long | **12** | 4 | 1 (poster) |
| 1 | cam_1 | bytetrack | 11 | 4 | 4 (poster fragments) |
| 1 | cam_1 | bytetrack_long | **9** | 4 | 2 (poster fragments) |

cam_2 and attendance_cam are unchanged (no static tracks). The rule was tightened afterwards (width must also stay within 5 %,
sideways movement < 2.2 %) because the first version also removed P2 sitting still for all of take 4
in cam_2. With the tightened rule the `bytetrack_long` numbers above are unchanged; plain `bytetrack`
on take 1 keeps one more poster fragment (12 IDs instead of 11). The committed `data/tracks/` files are
`bytetrack_long` + static filter.

Why `bytetrack_long`: with no frame-level ground truth yet, ID switches cannot be measured
directly. The proxy used is extra IDs = IDs kept − real people (same people, fewer IDs = fewer
switches). `bytetrack` → `bytetrack_long`: take 3 cam_1 12 → 9, cam_2 11 → 10, attendance_cam 1 → 1;
take 1 cam_1 11 → 7, cam_2 3 → 3, attendance_cam 0 → 0. It is never worse. Real people per camera
come from `data/ground_truth/take<N>.csv`.

Where the extra IDs come from (take 1 tracks lined up against `take1.csv` by time):

- **attendance_cam** is clean: one track per person, start/end within ~0.2 s of the ground truth.
- **cam_1 corridor** is clean too: one track per person while they walk to the door (e.g. P4
  3.8–7.3 s vs 3.5–7.0 s in the ground truth).
- **cam_1 extra IDs** are (a) people seen through the glass inside the classroom, and (b) a false
  positive: the poster of a man in a suit on the classroom wall (left of the window) is detected as a
  person in every frame of both takes (take 3: cam_1 track 3). The static filter now removes it.
- **cam_2** loses people while they sit behind P4 or a table and gives them a new ID when they
  reappear (P1, P2 get 2–3 IDs each in take 1).

Processing fps in the CSV is the wall-clock rate of that run on MPS; the take-1 runs (29–36 fps)
were slower than the first take-3 runs (59–81 fps) on the same laptop, so treat fps as rough until the
B9 benchmark measures it under controlled conditions.

Full numbers: `data/eval/tracking_baseline.csv` (column `take`). Reproduce with
`--take <N> --out-dir runs/compare/<name> --eval-csv data/eval/tracking_baseline.csv --real-people cam_1=4 cam_2=4 attendance_cam=<3 for take 3, 4 for take 1>`.

## 5. Check the backend

```bash
cd backend && uvicorn app.main:app --port 8000
curl http://localhost:8000/api/tracks/cam_1      # "source": "yolo11n+bytetrack", not "mock"
```

The backend serves `data/tracks/take<N>/<cam_id>.json` (`?take=N`, default: the take in
`data/video_config.json`), else the mock file for the default take. Then open
`http://localhost:5173` and press **Run demo videos**. The backend streams the original `.webm`;
its real duration matches the converted MP4 within 0.05 s, so the `t` values line up.

## 6. Ground truth: `data/ground_truth/take<N>.csv`

One file per take, drafted by AI from frames sampled every 0.5 s (0.1–0.2 s around entries and
exits in take 3):

| file | scenario | status |
| --- | --- | --- |
| `take1.csv` | simple case: P4, P1, P2, P3 walk in one at a time (~4 s, 17 s, 29 s, 39 s), each checks in and sits down | `AI draft`, not yet checked |
| `take3.csv` | P1, P2, P3 walk in together and check in as a group; P4 is already seated | checked by the team (2026-11-17) |

People (same labels in every take): `P1` red jersey, `P2` grey T-shirt, `P3` navy jersey #27 with
glasses, `P4` the person with red hair and a grey shirt (seated in take 3, walks in first in take 1).
`P4` is **Le Mai Chi** (`SWH02378` in `data/mock/students.csv`), matched by eye to the enrolment
photos in the team Drive folder `AppliedML/Mai Chi/`. P1–P3 have no photos yet, so they stay
unnamed.
cam_1 and cam_2 also see people through the glass between the corridor and the room; those
sightings have their own `seen` rows. Columns:

```
person,cam_id,appear_s,disappear_s,event,notes
```

| column | meaning |
| --- | --- |
| `person` | a stable label for the real person across all cameras and rows, e.g. `P1`, `P2`, or the student ID from `data/mock/students.csv` if known. Same person = same label on every camera. |
| `cam_id` | `cam_1`, `cam_2` or `attendance_cam` |
| `appear_s` | seconds from the start of **that camera's** video when the person first becomes visible (any part of the body) |
| `disappear_s` | seconds when the person is last visible. For a `check_in`/`enter_class`/`leave_class` row, use the moment of the event for both `appear_s` and `disappear_s` |
| `event` | one of the four values below |
| `notes` | free text: occlusions, people walking together, unsure cases. Avoid commas or wrap the field in double quotes |

Events:

| event | meaning |
| --- | --- |
| `seen` | the person is visible on this camera between `appear_s` and `disappear_s`. If they leave and come back, add another `seen` row |
| `check_in` | on `attendance_cam`: the person faces the doorway camera to be checked in (the moment the face is clearly visible) |
| `enter_class` | the person crosses the doorway into the classroom (feet past the door line) |
| `leave_class` | the person crosses the doorway out of the classroom |

Timing conventions:

- Times are seconds from the start of each camera's own video, the same clock as `t` in
  `data/tracks/take<N>/*.json`. Use the player's time display; 0.1 s precision is enough.
- Do **not** correct for the camera clocks: CAM 2's device clock runs ~23.4 s ahead in the file
  names, but the three videos of a take were recorded together (see the root README) and
  `offset_s` in `data/video_config.json` is 0. If you notice a camera is out of sync, say so in `notes`.
- Visible = at least about a quarter of the body on screen. If unsure, write it in `notes`.
- One row per (person, camera, visit) for `seen`; one row per event otherwise.

When you have checked a row, replace `AI draft` in its `notes` with `AI-drafted and user-confirmed (<date>)`.

## 7. Floor-map calibration

`data/calibration/room204_map.json` is a simple top-down model of the corridor + Room 204 (not
measured): corridor `x < 0.3`, classroom door on the corridor wall at `y` 0.79–0.96, glass window at
`y` 0.40–0.76, map scale about 3.4 m per 0.3 in `x` and 7 m per 1.0 in `y`.

`notebooks/02_homography.ipynb` saves each camera's first frame to
`data/calibration/<cam_id>_frame.png`, builds four image/map point pairs per camera, writes
`data/calibration/<cam_id>_homography.json`, and checks the result against the take-3 tracks.
`foot_to_map(box, H)` maps a box's bottom-centre (the feet) to the map; `box_to_map(cam, box, H)`
also handles the cases below.

There are no floor markers in the recordings, and each view only shows the corridor-wall base, so
the pairs come from `ground_model.py` (an estimate):

1. Each camera is a pinhole camera with an assumed 70° horizontal field of view.
2. Its height and horizon row are fitted from the tracked people, assuming a standing person is
   1.7 m tall (feet row = horizon + height / 1.7 × box height): cam_1 ≈ 0.85 m, cam_2 ≈ 1.13 m.
3. The two door jambs (floor pixels picked on the frame PNGs) fix the camera's direction and its
   position on the map: cam_1 ≈ (0.07, 0.27) facing south-east, cam_2 ≈ (0.79, 0.49) facing west.
4. Four floor pixels are projected with this model and fed to `cv2.findHomography`.

Check on take 3 (people's feet on visible floor): cam_1 corridor walk 91 % in the corridor, people at
the door 100 % at the door; cam_2 people at the door 98 %, people in the room 98 % inside the room.
Both cameras put the people waiting at the door at `y` ≈ 0.79.

Limits:

- `attendance_cam` sees faces, not feet, so it has no homography: a person it detects is placed at
  the door (`cameras.attendance_cam` in the map file).
- A box touching the bottom edge has no feet in view, and a seated person behind a table (cam_2) or
  someone seen through the glass (cam_1) has the box bottom on the table or the wall, not the floor.
  `box_to_map` returns `None` for boxes touching the bottom edge; the other two cases still need to be
  filtered by whoever uses the positions (e.g. ignore cam_1 points with `x > 0.3`).
- Positions are approximate (roughly ±0.5 m). For accurate positions, put four tape crosses on the
  floor, measure them on the map, and replace the pairs in `CALIB`.
