# Tracking (Mai Chi)

Person detection + tracking for the three demo cameras. Output feeds the Home page through
`GET /api/tracks/{cam_id}` (see the root README, "Data contract for bounding boxes").

All commands run from the repo root.

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
duration, and the three cameras within 1 s of each other. Take 4: 31.40 / 31.40 / 31.03 s.

## 4. Precompute the demo tracks

```bash
ml/.venv/bin/python ml/tracking/precompute_tracks.py --cam all \
    --tracker ml/tracking/configs/bytetrack_long.yaml
```

Writes `data/tracks/{cam_1,cam_2,attendance_cam}.json` (committed; the demo needs them).
Defaults: `yolo11n.pt` (pre-trained, not fine-tuned), class 0 (person), `--conf 0.4`,
keyframe every 3rd frame (`--every-n 3`), tracks with fewer than 5 keyframes dropped
(`--min-keyframes 5`). `t = frame_index / fps` of the processed file; `box = [x, y, w, h]` as
fractions of the frame with `x, y` the top-left corner. `global_id` is the camera-local ByteTrack
ID until cross-camera matching replaces it. `attendance_cam` uses the same person detector for now.

### Tracker choice (E1 baseline, take 4)

The committed `data/tracks/` files come from **`configs/bytetrack_long.yaml`**: Ultralytics'
`bytetrack.yaml` with `track_buffer: 90` instead of 30, so a lost person is kept alive for ~3 s
at 30 fps instead of ~1 s.

| cam_id | tracker | IDs before filtering | IDs kept | real people |
| --- | --- | --- | --- | --- |
| cam_1 | bytetrack | 20 | 16 | 4 |
| cam_1 | bytetrack_long | 17 | 13 | 4 |
| cam_2 | bytetrack | 24 | 15 | not counted |
| cam_2 | bytetrack_long | 20 | 14 | not counted |
| attendance_cam | bytetrack | 5 | 4 | not counted |
| attendance_cam | bytetrack_long | 5 | 4 | not counted |

Why `bytetrack_long`: with no frame-level ground truth yet, ID switches cannot be measured
directly. The proxy used is extra IDs = IDs kept − real people (same people, fewer IDs = fewer
switches). On cam_1 (4 people, counted by watching the annotated video) that is 12 for
`bytetrack` and 9 for `bytetrack_long`; it also produces fewer IDs on cam_2 and the same on
attendance_cam. Both are still far above 4, so each person is split into several IDs:
cross-camera matching / Re-ID has to merge them.

Full numbers incl. processing fps: `data/eval/tracking_baseline.csv`. Reproduce with
`--out-dir runs/compare/<name> --eval-csv data/eval/tracking_baseline.csv --real-people cam_1=4`.

## 5. Check the backend

```bash
cd backend && uvicorn app.main:app --port 8000
curl http://localhost:8000/api/tracks/cam_1      # "source": "yolo11n+bytetrack", not "mock"
```

The backend serves `data/tracks/<cam_id>.json` when it exists, else the mock file. Then open
`http://localhost:5173` and press **Run demo videos**. The backend streams the original `.webm`;
its real duration matches the converted MP4 within 0.05 s, so the `t` values line up.

## 6. Ground truth: `data/ground_truth/take<N>.csv`

One file per take, header only until someone annotates it by watching the videos:

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
  `data/tracks/*.json`. Use the player's time display; 0.1 s precision is enough.
- Do **not** correct for the camera clocks: CAM 2's device clock runs ~23.4 s ahead in the file
  names, but the three videos of a take were recorded together (see the root README) and
  `offset_s` in `data/video_config.json` is 0. If you notice a camera is out of sync, say so in `notes`.
- Visible = at least about a quarter of the body on screen. If unsure, write it in `notes`.
- One row per (person, camera, visit) for `seen`; one row per event otherwise.

Example (illustrative only, not real annotations):

```
P1,cam_1,2.0,9.5,seen,
P1,attendance_cam,10.8,10.8,check_in,
```

## 7. Floor-map calibration

`notebooks/02_homography.ipynb` saves each camera's first frame to
`data/calibration/<cam_id>_frame.png`. Pick four floor points per camera (pixel `(x, y)` in that
image) and the same four points on the Room 204 map (normalised to `[0, 1]`; the corridor is
`x < 0.3`), put them in `image_points` / `map_points`, and rerun: it writes
`data/calibration/<cam_id>_homography.json`. `foot_to_map(box, H)` maps a track box's bottom-centre
(the feet) onto the map.
