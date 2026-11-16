# Hawkeye — multi-camera classroom attendance

COS30082 Applied Machine Learning team project. Three cameras (corridor, classroom, doorway) track every person with a numeric ID; the doorway **attendance camera** checks liveness, recognises the face and reads emotion, then the ID becomes `ID n · Name` on every camera. Hawkeye logs check-in, entry, exit and total time in class.

> Status: **template**. The Home page runs on mock data and plays the recorded demo videos. Every model is a stub marked `TODO` with its owner.

## Repo layout

```
backend/            FastAPI server (API + video streaming)
  app/main.py       builds the app; routes live in app/api/ (one file per area)
  app/core/         plug-in pipeline: stage registry, event bus, runner (configured by backend/pipeline.json)
  app/features/     one folder per innovation feature; see app/features/README.md
  app/pipeline/     one stub per model / step (detector, tracker, liveness, recognizer, emotion, matcher, attendance)
  app/db/schema.sql SQLite tables (not wired yet)
frontend/           Vue 3 + Vite web app (Home page built, other pages placeholders)
  src/pages.js      page registry: add one entry to get a route + sidebar item
data/
  mock/             mock data: students.csv + courses.csv (from the team metadata sheet), session.json, tracks/
  video_config.json which recording each camera plays in the demo
ml/                 training code per model (placeholders + the tracking precompute script)
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

Press **Run demo videos** on the Home page. The three videos stream from the backend and play in sync. No backend? Use **Load from computer** and pick one file per camera.

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

`data/video_config.json` lists all 9 synced takes and which take the demo plays (`"take"`). Change that number to play another take. Files are matched across cameras by take number, not by the timestamp in the filename: the CAM 2 device clock runs about 23.4 s ahead of the others in every take. Use `offset_s` per camera to fine-tune sync.

## Who owns what

| Part | Owner | Files |
| --- | --- | --- |
| Integration, multi-camera tracking, cross-camera matching | Mai Chi | `backend/app/pipeline/{detector,tracker,matcher}.py`, `ml/tracking/` |
| Web app, database, camera streaming | Đức Mạnh | `frontend/`, `backend/app/main.py`, `backend/app/db/` |
| Face embedding models (classification + triplet) | Thuận Minh | `ml/face_recognition/`, `backend/app/pipeline/recognizer.py` |
| Anti-spoofing | Hồng Minh | `ml/anti_spoofing/`, `backend/app/pipeline/liveness.py` |
| Emotion | Minh Thành | `ml/emotion/`, `backend/app/pipeline/emotion.py` |

## Data contract for bounding boxes

The frontend draws boxes from `GET /api/tracks/{cam_id}`. The backend serves `data/tracks/<cam_id>.json` if it exists (real output), else `data/mock/tracks/<cam_id>.json`.

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
