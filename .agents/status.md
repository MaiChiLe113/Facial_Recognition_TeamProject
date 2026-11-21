# Status

Last updated: 2026-11-21. Update this file at the end of every step.

## Branch

All work happens on **one branch: `feature/backend-structure`**. It holds the Vue migration, the backend restructure and this `.agents/` folder. Commit every step there.

- Do not create other branches.
- Do not merge into `main` or push unless the user asks.
- `main` stays as the original template (React frontend, single `main.py`).

## 2026-11-21: multi-person naming + progress check (Mai Chi, not committed yet)

**New from teammates since 2026-11-18:**
- Thuận Minh: `ml/face_recognition/01_train_classification.ipynb`, `02_train_triplet.ipynb`,
  `03_evaluate_verification.ipynb`. Selected model: triplet + cosine, threshold ≥ 0.5254, holdout AUC 0.954,
  TAR 54.1 % at FAR 2.0 %. `backend/app/pipeline/recognizer.py` is still a stub; weights are on his machine.
- Everyone uploaded enrolment photos to their Drive folder (Đức Mạnh 14, Hồng Minh 12 HEIC, Thuận Minh 23,
  Minh Thành 30). Thuận Minh's card is on the Drive as `student_card_image/TMinh.jpg`.

**Changed (Mai Chi's area unless noted):**
- `ml/face_recognition/name_tracks.py`: a face crop votes only for its best-matching student; enrolment
  retries smaller sizes when no face is found (phone close-ups); HEIC via `pillow-heif` when `sips` is
  missing (Windows); `--students <csv>` option.
- `data/mock/students.csv` (shared): Thuận Minh's `student_card` = `AppliedML/student_card_image/TMinh.jpg`.
- `data/tracks/take{1,3,4,8}/*.json`: names from the full rerun below.
- Docs: root `README.md` status, `ml/face_recognition/README.md`, `ml/tracking/README.md`.
- Rerun locally on all 8 takes (2026-11-21, all five enrolled, Minh Thành from a scratch roster with
  `--students`): take 1 all four named (Mai Chi, Thuận Minh, Đức Mạnh, Hồng Minh) on all three cameras;
  take 3 Đức Mạnh, Thuận Minh, Hồng Minh on attendance_cam only (crowded door, no handoff) plus a short
  second Đức Mạnh track (ID 5); takes 4 and 8 Hồng Minh on all three cameras; takes 2, 5, 6, 7 unknown
  (no usable face). Per-track counts in `ml/face_recognition/README.md`. **Next:** check the labels by
  eye on the Demo page. Take 3 checked (correct; ID 5 = Đức Mạnh after a tracker ID switch from ID 1).
  Take 1 checked (all attendance names and cam_1 / cam_2 handoffs correct; seated people later get new
  unnamed IDs on cam_2). Takes 4 and 8 still to check.
- Minh Thành was added to `students.csv` as Do Minh Thanh (105550306 / SWH01234) and removed from the
  placeholder list in `data/mock/session.json`; `backend/tests/test_db.py` now checks he is on the roster. He is not in any recorded
  take, and he was correctly not named on any track (at most 1 crop per track matched him).
- Seen, not fixed: the Demo page shows `Infinity:NaN` as the duration for `.webm` videos (frontend, Đức Mạnh).

**Progress of Mai Chi's parts (tracking + multi-camera):**

| Part | Done | Not done |
| --- | --- | --- |
| Detection + ByteTrack (Phase A) | YOLO11n + ByteTrack precomputed for all 8 takes; `bytetrack_long` (3 s buffer) chosen; static-object filter; E1 ID-count baseline on takes 1 and 3 (`data/eval/tracking_baseline.csv`) | MOT metrics vs ground truth (ID switches, IDF1); take 1 ground truth still a draft, takes 2 and 4–8 have none; YOLO is not fine-tuned (brief: no fully pre-trained model without further training); live `detector.py` / `tracker.py` stubs raise `NotImplementedError` |
| Multi-camera (Phase B) | T1 approximate floor-map homographies for cam_1 / cam_2; T2 door handoff of names (`link_names.py`), working on takes 1 and 8 | T3 appearance Re-ID (OSNet) and T4 face check on cam_2; one shared global ID across cameras (`GlobalMatcher` in `matcher.py` is a stub); in/out time error vs ground truth |

## 2026-11-18: SQLite wired (task 1, Đức Mạnh)

- `backend/app/db/`: `schema.sql` (tables now `IF NOT EXISTS`; added `placeholder_students`; `attendance` gained
  `global_id`, `entry_at`, `exit_at`, `minutes`, `attended` override; `events` gained `session_id`, `message`),
  `__init__.py` (`connect`, `init_db`), `seed.py`, `queries.py`. `mock_store.py` removed.
- On startup `init_db()` creates `data/hawkeye.sqlite3` and seeds it from `students.csv`, `courses.csv`,
  `session.json`, `past_sessions.json` (moved from `frontend/src/mock/sessions.js`) and `video_config.json`.
  Re-seed: `python -m app.db.seed --reset` (from `backend/`).
- Routes from SQLite: `/api/dashboard` (newest session), `/api/students`, `/api/courses`, `/api/sessions`,
  `PATCH /api/sessions/{id}/attendance/{student_id}` (History edits are saved), `/photos/{id}`.
  Attendance-cam status and map positions still come from `session.json`.
- `sqlalchemy>=2.0` added to `requirements.txt`. Tests: 19 OK (`tests/test_db.py` new).

## 2026-11-18: UI changes (Đức Mạnh)

- Home is the live view: each of the 3 camera frames has a "+" box that asks for this device's camera
  (`CameraCard` prop `live`, `getUserMedia`, device picker when several). "Run demo videos" and the Boxes
  tick removed. Frames are not sent to the backend yet (task 5).
- Demo: Boxes tick removed (boxes always on); adds Event log, Room map and Class roster (mock dashboard).
- "offline · mock data" badge removed on every page.
- Class page merged into History (`/class` redirects). History shows the roster of the picked (or newest)
  session; Attended and Status are editable in the page only (TODO: PATCH route to save).
- Roster photos: student card image from the Drive (`student_card` column) via `GET /photos/{student_id}`
  (`backend/app/api/photos.py`, `HAWKEYE_DRIVE_ROOT`, default two levels above `HAWKEYE_VIDEO_ROOT`).
  `manh.pdf` page 1 converted to `student_card_image/manh.png` on the Drive and the PDF deleted. Others
  without a card show initials.

## 2026-11-17: tracking and naming work (Mai Chi)

Done on Mai Chi's machine, on top of `main` after PR #1 was merged. Full detail: `ml/tracking/README.md`
and `ml/face_recognition/README.md`.

**New (Mai Chi's area, `ml/` and data):**
- `ml/tracking/`: `paths.py` (video paths), `precompute_tracks.py` (YOLO11n + ByteTrack, static-object
  filter), `configs/bytetrack_long.yaml`, `ground_model.py` + `notebooks/02_homography.ipynb` (approximate
  floor-map homographies for cam_1 / cam_2), `link_names.py` (name handoff at the door),
  `notebooks/01_explore.ipynb` (video checks, 30 fps conversion).
- `ml/face_recognition/name_tracks.py`: baseline face naming with OpenCV YuNet + SFace until Thuận Minh's
  model exists. Only Le Mai Chi has enrolment photos; she is named from 6.4 s in take 1 on all cameras.
- Data: `data/tracks/take1..8/` (committed boxes), `data/ground_truth/take1.csv` (draft, not yet checked) and `take3.csv`
  (checked), `data/calibration/` (frames, `room204_map.json`, homographies), `data/eval/tracking_baseline.csv`.

**Changed in Đức Mạnh's files (please review):**
- `backend/app/api/demo.py`, `services/videos.py`: `/api/demo/config`, `/videos/{cam}` and
  `/api/tracks/{cam}` take an optional `?take=N` (default: `"take"` in `data/video_config.json`). Tracks are
  read from `data/tracks/take<N>/`; the old `data/tracks/<cam>.json` and the mock are fallbacks for the
  default take only. Responses only gained fields (`default_take`, `?take=` in video URLs).
- `frontend/src/pages/Demo.vue`: plays any take with its boxes; Source column removed.
  `Demo.vue` and `Home.vue`: "Load from computer" (video upload) removed at the user's request.
- `frontend/src/components/CameraCard.vue`: the frame follows the video's aspect ratio (no black bars);
  labels honour the optional `name_from` and show the given name ("Mai Chi").
- `frontend/src/api.js`: `fetchDemoConfig(take)` and `fetchTracks(camId, take)`; offline fallback kept.
- `data/mock/students.csv` + `backend/app/db/schema.sql`: new `student_card` column; Thuận Minh and Hồng
  Minh get course `[1]`, as in the metadata sheet.
- `data/video_config.json`: the failed old take 1 removed (its videos deleted from Drive), takes
  renumbered 1–8, default take 4 → 3, measured lengths.

Checks run: backend `unittest` (13 OK), `npm run build`, every take plays in the Demo page with boxes,
Mai Chi's label changes from Unknown to her name at check-in on all three cameras.

**Next for this workstream:** Re-ID (Phase B) for one shared ID per person across cameras and for
tracks after occlusion or seen through the glass; enrolment photos for the other students.

## Task list from the user (in order)

| # | Task | State |
| --- | --- | --- |
| 0a | Frontend: React → Vue 3 + npm | Done |
| 0b | Backend: scalable structure, features plug into the pipeline without breaking others | Done |
| 0c | Frontend pages: Attend Course, Class, History, Demo and Add person, in the Home page style, following the Chi document's UI section. They run on mock data (`src/mock/sessions.js` plus `data/mock`) through `api.js` fallbacks; the backend routes they expect are listed at the top of the pages section in `api.js` | Done (frontend only) |
| 1 | ~~SQLite with SQLAlchemy from `backend/app/db/schema.sql`; seed script for `data/mock/students.csv` and `courses.csv` (a `courses` value like `"[1,2]"` becomes `enrollments` rows); `GET /api/dashboard` reads students and courses from the DB while attendance, events and map still come from `data/mock/session.json` ~~ | Done 2026-11-18 (see above) |
| 2 | Add person page + `POST /api/students`: name, Student ID (VN, e.g. `SWH02701`), Student ID (AU), year, course checkboxes, 10–20 photos saved to `data/photos/<student_id_vn>/` (git-ignored). Leave a TODO where `recognizer.embed` computes embeddings; do not implement embeddings | Not started |
| 3 | ~~Class page: course table per session (name, student ID, status, check-in, entry, exit, total time, "Logs" link to that student's events); reuse `ClassRoster`~~ | Merged into History 2026-11-18 |
| 4 | History page: past sessions + event log, filter by student and date | Not started |
| 5 | Camera page `/camera/<cam_id>`: `getUserMedia`, JPEG frames at ~10 fps over WebSocket to `/ws/camera/{cam_id}`; the backend only counts frames for now; Home shows that camera as live. WebRTC (aiortc) comes later | Not started |

## Plan for step 1 (agreed shape)

**New files** in `backend/app/db/`:
- `__init__.py`
- `database.py`: engine, session and `init_db()`, which runs `schema.sql`. The DB file is `data/hawkeye.sqlite3`, overridable with `HAWKEYE_DB_PATH`.
- `models.py`: models for `Student`, `Course` and `Enrollment` only.
- `seed.py`: run with `python -m app.db.seed`. Idempotent upserts.

**Changed files:**
- `schema.sql`: `CREATE TABLE IF NOT EXISTS`.
- The dashboard builder reads from the DB. Put it in `services/` and keep the JSON shape identical, including roster order and `"source": "mock"`.
- `requirements.txt`: add `sqlalchemy>=2.0`.

**Proposed defaults:** auto-seed on startup when `students` is empty, and keep `schema.sql` as the single source of truth for the tables.

**Wiring the embeddings later:** the `recognize` stage reads its gallery from `engine.shared["gallery"]`. Fill it from `face_embeddings` once that table has data.

## Known TODOs left in code

- `core/stages/attendance_cam.py`: the liveness stage keeps one crop buffer for the main face. It needs one buffer per global ID once the matcher links faces to tracks.
- `core/subscribers.py`: `AttendanceLog` should publish `in` / `out` events back onto the bus.
- `main.py`: still to build `/ws/camera/{cam_id}`, `/ws/dashboard` and `POST /api/students`.
- The design doc still says "React + Vite" and points to `frontend/src/pages/Home.jsx` (now `Home.vue`). It is shared, so the team fixes it.
