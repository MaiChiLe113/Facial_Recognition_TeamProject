# Hawkeye — multi-camera classroom attendance

COS30082 Applied Machine Learning team project. Three cameras (corridor, classroom, doorway) track every person with a numeric ID; the doorway **attendance camera** checks liveness, recognises the face and reads emotion, then the ID becomes `ID n · Name` on every camera. Hawkeye logs check-in, entry, exit and total time in class.

> Status: the Home page runs on mock data for the roster and events. The Home page (source switch **Recorded**) plays the recorded takes with **real person boxes** (YOLO11n + ByteTrack, precomputed), and people are recognised at check-in on the attendance camera and named on all three cameras (all four people in take 1, three in take 3, Nguyen Hong Minh in takes 4 and 8; all five members have enrolment photos). Live mode: phones on the same Wi-Fi act as the three cameras (`/camera`) and the host's **Home** page (source switch **Live**, the default) shows each stream with person tracking (corridor, classroom) or face, liveness, recognition and emotion (doorway). The cross-camera matcher and the attendance rules are still stubs marked `TODO` with their owners.

## Repo layout

```
backend/            FastAPI server (API + video streaming)
  app/main.py       builds the app; routes live in app/api/ (one file per area)
  app/core/         plug-in pipeline: stage registry, event bus, runner (configured by backend/pipeline.json)
  app/features/     one folder per innovation feature; see app/features/README.md
  app/pipeline/     non-model steps: detector, tracker (done), matcher, attendance (stubs); the models are in ml/<feature>/
  app/db/schema.sql SQLite tables (not wired yet)
frontend/           Vue 3 + Vite web app (Home page built, other pages placeholders)
  src/pages.js      page registry: add one entry to get a route + sidebar item
data/
  mock/             seed + mock data: roster.json (courses + students, seeds a new database), session.json, tracks/
  photos/           face photos from the Add person page (git-ignored)
  video_config.json which recording each camera plays in the demo
  tracks/take<N>/   real boxes per take and camera (made by ml/tracking, served by /api/tracks)
  ground_truth/     who appears when, per take (take1.csv, take3.csv), for evaluation
  calibration/      first frames, Room 204 floor map, camera -> map homographies
  eval/             experiment results (tracking_baseline.csv)
ml/                 training code per model; ml/tracking/ = detection, tracking, naming (see its README)
```

## Run it

**1. Backend** (Python 3.10+)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set HAWKEYE_VIDEO_ROOT to your "video data" folder
uvicorn app.main:app --reload --port 8000
```

**2. Frontend** (Node 18+)

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

Press **Run demo videos** on the Home page. The three videos stream from the backend and play in sync.

**Demo with other devices' cameras (same Wi-Fi):** run `npm run dev:lan` instead and open the printed `https://<host IP>:5173` address on each device. Full steps: [`docs/LAN_DEMO.md`](docs/LAN_DEMO.md). To use phones as the three cameras: open `/camera` on each phone and **Home** (Live) on the host, which shows every stream with detection, tracking and recognition.

## Adding to the pipeline

`backend/pipeline.json` lists the stages each camera runs, in order, and which features are on. To add a per-frame step, write a stage in `app/core/stages/`. To react to events (check-in, spoof, in/out), write a feature in `app/features/`. Neither needs changes to anyone else's file. A part that fails is skipped and reported; the rest keeps running.

`GET /api/pipeline/status` shows every stage, subscriber and feature as `ready`, `not_ready` (still a stub), `failed` or `disabled`. Run the tests from `backend/` before a pull request:

```bash
python -m unittest discover -s tests -t .
```

Step-by-step guide: [`backend/app/features/README.md`](backend/app/features/README.md).

## Demo videos

The recordings live in the team Google Drive folder `AppliedML/video data/` (one sub-folder per camera). Each camera device has its own stream ID:

| Camera | Folder | Stream ID | Shown as |
| --- | --- | --- | --- |
| Corridor | `cam_1` | `sCi8Jvd` | CAM 1 |
| Classroom | `cam_2` | `pDHjQPf` | CAM 2 |
| Doorway | `attendance_cam` | `2SiEwN8` | Attendance camera |

`data/video_config.json` lists all 8 synced takes and which take the Home page plays (`"take"`, currently 3). Home in Recorded mode (`/?source=recorded&take=N`; the old `/demo` route redirects there) plays any take: pick it in the take menu or the table and press Play. Files are matched across cameras by take number, not by the timestamp in the filename: the CAM 2 device clock runs about 23.4 s ahead of the others in every take. Use `offset_s` per camera to fine-tune sync.

## Tracking and naming (Mai Chi)

The boxes and names you see in the demo are precomputed from the recordings. Full guide: [`ml/tracking/README.md`](ml/tracking/README.md). Quick version (macOS paths; on Windows use `ml/.venv/Scripts/python`):

```bash
python3.12 -m venv ml/.venv && ml/.venv/bin/pip install -r ml/tracking/requirements.txt   # once; also install FFmpeg
for t in 1 2 3 4 5 6 7 8; do
  ml/.venv/bin/python ml/tracking/precompute_tracks.py --cam all --take $t --tracker ml/tracking/configs/bytetrack_long.yaml
done
ml/.venv/bin/python ml/face_recognition/name_tracks.py --take all     # always after precompute: it resets names
```

`name_tracks.py` needs two small OpenCV face models in `ml/face_recognition/models/` (download commands in [`ml/face_recognition/README.md`](ml/face_recognition/README.md)).

1. **Tracking** (`precompute_tracks.py`): YOLO11n (pre-trained) + ByteTrack with a 3 s buffer, people only, every 3rd frame kept, short tracks and objects that never move (a poster on the classroom wall) dropped. Output: `data/tracks/take<N>/<cam_id>.json`.
2. **Naming at check-in** (`ml/face_recognition/name_tracks.py`): a baseline until Thuận Minh's model is trained. OpenCV YuNet + SFace compare faces on the attendance camera with each student's enrolment photos (`photo_folder`) and student card (`student_card`) of every student in the backend's database. All five members have photos in their Drive folders (`AppliedML/<your name>/`). New students are registered on the **Add person** page (`POST /api/students`, photos saved to `data/photos/`); rerun after registering someone.
3. **Name on every camera** (`ml/tracking/link_names.py`, run by step 2): the cam_1 / cam_2 track standing at the classroom door while that person checks in gets the same name, from the check-in time on.

Takes: the old take 1 was a failed recording and was deleted from the Drive folder on 2026-11-17; the other takes were renumbered (old 2–9 → 1–8, the old demo take 4 is now **take 3**). `data/video_config.json` already uses the new numbers.

## Who owns what

| Part | Owner | Files |
| --- | --- | --- |
| Integration, multi-camera tracking, cross-camera matching | Mai Chi | `backend/app/pipeline/{detector,tracker,matcher}.py`, `ml/tracking/` |
| Web app, database, camera streaming | Đức Mạnh | `frontend/`, `backend/app/main.py`, `backend/app/db/` |
| Face embedding models (classification + triplet) | Thuận Minh | `ml/face_recognition/` (`infer.py` + `face_recognition.pt`) |
| Anti-spoofing | Hồng Minh | `ml/anti_spoofing/` (`infer.py` + `anti_spoofing.pt`) |
| Emotion | Minh Thành | `ml/emotion/` (`infer.py` + `emotion.pt`) |

## Data contract for bounding boxes

The frontend draws boxes from `GET /api/tracks/{cam_id}?take=N` (no `take` = the take in `data/video_config.json`). The backend serves `data/tracks/take<N>/<cam_id>.json` if it exists (real output, made by `ml/tracking/precompute_tracks.py`); for the default take it falls back to `data/mock/tracks/<cam_id>.json`. Videos stream from `GET /videos/{cam_id}?take=N`.

```json
{
  "cam_id": "cam_1",
  "source": "mock | yolov8n+bytetrack",
  "tracks": [
    { "global_id": 12, "name": null,
      "keyframes": [ { "t": 0.0, "box": [0.35, 0.20, 0.22, 0.75] }, { "t": 8.0, "box": [0.50, 0.22, 0.22, 0.74] } ] }
  ]
}
```

`t` = seconds from the start of that camera's video. `box` = `[x, y, w, h]` as fractions of the frame (0–1). The frontend interpolates between keyframes, so a detector can write every frame or every few frames.

Real output has `"source": "yolo11n+bytetrack"`. Optional track fields, added for naming (old readers can ignore them):

| field | meaning |
| --- | --- |
| `name_from` | seconds; show `name` only from this time on (the check-in moment). Before it the box reads `ID n · Unknown` |
| `name_source` | where the name came from, e.g. `attendance_cam ID 1 (door handoff)` |

`global_id` is still the per-camera ByteTrack ID: the same person can have different numbers on different cameras until the Re-ID matcher (Phase B) assigns one shared ID.
