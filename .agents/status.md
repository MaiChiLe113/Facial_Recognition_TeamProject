# Status

Last updated: 2026-11-21. Update this file at the end of every step.

## Branch

All work happens on **one branch: `feature/backend-structure`**. It holds the Vue migration, the backend restructure and this `.agents/` folder. Commit every step there.

- Do not create other branches.
- Do not merge into `main` or push unless the user asks.
- `main` stays as the original template (React frontend, single `main.py`).

## 2026-11-23: live detector (Mai Chi, branch `tracking/live-detector`)

- `backend/app/pipeline/detector.py` implemented: `detect_people()` = YOLO11n (class 0, conf 0.4, same as the precomputed
  tracks; `ml/tracking/yolo11n.pt`, downloaded by Ultralytics if missing), `detect_faces()` = OpenCV YuNet (score 0.8,
  faces < 20 px dropped, largest first; `ml/face_recognition/models/face_detection_yunet_2023mar.onnx`, now committed with
  `git add -f`, 230 KB). Boxes `(x, y, w, h, score)` in pixels, clipped to the frame; models load once, on first use.
  Overrides: `HAWKEYE_PERSON_DETECTOR`, `HAWKEYE_FACE_DETECTOR`.
- Unblocks the attendance-camera pipeline: on take 1 frames, `detect_faces -> liveness -> recognize -> emotion` all report
  `ready` (17 / 57 / 7 / 6 ms per frame on Mai Chi's Mac). Hồng Minh's PR #6 asked for this.
- Seen while testing (Thuận Minh's area, not changed): with a 2-person test gallery, a person not in the gallery scored
  cosine 0.68 while an enrolled person scored 0.57 on doorway frames; check the recognizer on our camera faces.
- `backend/tests/test_detector.py`: 7 tests on the committed calibration frames (skip without OpenCV / Ultralytics).
- `requirements.txt`: `ultralytics>=8.3` added. Still stubs: `tracker.py`, `matcher.py`, `attendance.py`.

## 2026-11-23: emotion model trained and wired in (Minh Thành)

- `ml/emotion/emotion_training.ipynb` (run, outputs saved): small CNN, ResNet-18 on FER2013, ResNet-18 on FER2013 + AffectNet
  (Hugging Face `Mauregato/affectnet_short`, contempt dropped, faces cut with YuNet). Selected: ResNet-18 (ImageNet, conv1 +
  layer1 frozen) on FER2013 + AffectNet. Test accuracy: FER2013 0.707 (macro-F1 0.698), AffectNet 0.661 (0.632); the
  FER2013-only model gets 0.460 on AffectNet. Results in `ml/emotion/README.md` (plots in `results/emotion/`, git-ignored).
- `ml/emotion/infer.py` rewritten inside, same contract (`predict(face_crop, smooth=True)`, `reset()`, `HAWKEYE_EMOTION_WEIGHTS`):
  crop -> grayscale 48x48 -> 96x96 inside the model, probabilities averaged over the last second (`SMOOTH_SECONDS = 1.0`). Checkpoint keys:
  `state_dict`, `classes`, `face_size`, `img_size`, `mean`, `std`. `ml/emotion/emotion.pt` (44.8 MB, committed on `main` with `git add -f`) is written by the
  last notebook cell. Through `load_infer("emotion")`: 0.7055 on the FER2013 test set.
- Crop: the raw face box (Features demo `MARGIN["emotion"] = 0.0`) scores the same as a square crop with this model (0.633 vs 0.636), so no change needed there.

## 2026-11-23: innovative feature built: door audit + presence verification (Đức Mạnh, not committed yet)

- Code in `ml/presence_verification/` (see its `README.md`, manual tests in `TEST.md`, plan + deviations in `PLAN.md`):
  `trajectories.py` (tracks → map, valid area per camera), `door_audit.py` (crossings, Δt model, Hungarian, pair
  classifier, alerts D1/D2/D3), `presence.py` (features, rules R1–R5, model score), `simulate.py`, `train.py`,
  `evaluate.py`, `infer.py` (API for the backend), `tests/` (19 unit tests).
- Model file `presence_verification.joblib` and `outputs/` are git-ignored; rebuild with `train.py` (~2 min CPU).
- Backend plug-in `backend/app/features/presence_verification/` (switched on in `pipeline.json`): `GET /api/features/presence_verification/take/{take}`,
  `/model`, `/live`. Without the model file it shows `failed` in `/api/pipeline/status` and mounts no routes.
- Frontend: `PresencePanel.vue` on the Demo (MultiCam) page, map trails on `RoomMap.vue` (optional `trails` prop; red = alert).
- `RoomMap.vue` draws the 2D map from the team's FigJam design (board b8wiU877MrltPtUYAI4BiW, section node 19:6), copied into `frontend/src/roomLayout.js` (map pixels, 920 x 520). To change the map: edit it in Figma, then update that file. The Figma door gap is y 0.727 to 0.906; `data/calibration/room204_map.json` (used by the homographies and the presence trails) has it at 0.789 to 0.961, so the drawn door and the trails can differ slightly. The calibration file is Mai Chi's and was not changed. People dots and trails are still fractions of the map (x 920, y 520). The mock `door` / `cameras` fields of `session.json` are not drawn.
- New deps in `requirements.txt`: `scikit-learn`, `scipy`, `joblib` (installed in the repo-root `.venv`); matplotlib only for figures.
- Still open: tell Mai Chi (it reads `data/tracks/` and `link_names.py` names, never writes them), team OK for the new
  deps, record scripted fraud takes (all recorded takes are normal). Known real failure: take 3 gives D3 + D1 because
  the tracker switches IDs while three people stand in the doorway.

## 2026-11-22: models moved to `ml/`, Features demo page (Đức Mạnh, not committed yet)

- `backend/app/pipeline/{liveness,recognizer,emotion}.py` are gone. Each basic model is now `ml/<feature>/infer.py` plus the weights
  `ml/<feature>/<feature>.pt` for `face_recognition`, `anti_spoofing` and `emotion`. `backend/app/core/ml_models.py` finds them
  (`weights_file()`, `load_infer()`); the attendance-camera stages use it. `pipeline/` keeps only Mai Chi's detector, tracker and matcher.
- `ml/face_recognition/infer.py` is new (written from the notebook export format): `embed()` and `identify()`, threshold from the file
  (cosine >= 0.5254). `ml/face_recognition/face_recognition.pt` is a copy of `verification_fp32_v1/selected_model.pt`. Checked on real photos.
- `ml/emotion/infer.py` is new; it expects a ResNet-18 checkpoint in the format described in its docstring. (Model trained 2026-11-23, see above.)
- `ml/anti_spoofing/infer.py` is the old `liveness.py`; it reads `ml/anti_spoofing/anti_spoofing.pt` (the file is in place now, renamed from `liveness_mobilenetv2.pt`; checked on real faces: live, score 0.99, threshold 0.0239; not yet tried on printed photos or phone screens).
- New page **Features demo** (`/features-demo`, `frontend/src/pages/FeaturesDemo.vue`): tick face recognition / anti-spoofing / emotion,
  it streams webcam frames to `POST /api/features-demo/infer` (`backend/app/api/features_demo.py`, `services/features_demo.py`), draws the
  results. Recognition uses the registered students: the Drive enrolment photos (photo folder + student card) that MultiCam also uses, embedded on first use (`GET /api/features-demo/gallery`). Faces are found with OpenCV Haar (demo only); `pillow-heif` is needed for HEIC photos. A feature without weights shows a clear error.
- Features demo page has a **Recognition threshold** slider (shown when face recognition is ticked). `POST /api/features-demo/infer` takes an optional `?threshold=` (cosine, -1..1, else 400); left out = the threshold saved in the weights, which `GET /api/features-demo/status` now returns as `threshold` on the face_recognition entry. The choice is kept in the browser (`localStorage`), per viewer, not on the server. The pipeline's `recognize` stage still reads `options.threshold` from `pipeline.json`. The threshold actually used (custom or the weights' own) is logged in a `threshold` column of the session log and the CSV, next to `similarity`, on rows where recognition ran. Anti-spoofing has the same: a **Liveness threshold** slider (0..1), `?liveness_threshold=` on `/infer` (else 400), `threshold` on the anti_spoofing entry of `/status`, and a `liveness_threshold` CSV column. It is applied in `services/features_demo.py` by comparing the returned score (`score > 0 and score >= threshold`), because `ml/anti_spoofing/` is not ours to edit; the default is read through `infer._load()["threshold"]` (private, no public accessor). The `liveness` pipeline stage still has no threshold option. The status line under the camera shows `Live 97%` / `Spoof 88%` = how sure the shown label is (`liveness_confidence` on the face, 0.5 at the threshold up to 1.0; a distance to the decision boundary, not a calibrated probability); the raw P(live) stays in `liveness_score` and in the log.
- The Features demo page has a **Session log** panel (camera on to camera off, always shown). The "Save log (CSV)" box only decides
  whether that session is written to `logs/features_demo_<start time>.csv` (repo root, git-ignored, one row per face per frame) when the
  camera turns off (`POST /api/features-demo/log`; also sent with `sendBeacon` if the tab is closed while the camera is on).
- `requirements.txt` now lists torch, torchvision, numpy, pillow, opencv-python-headless (<5: OpenCV 5 has no CascadeClassifier).
- `runs/` no longer exists at the repo root; the `runs/**` rules in `.gitignore` are now obsolete. The notebooks still write to `runs/`
  when re-run (Thuận Minh's), which would recreate it.

## 2026-11-21: multi-person naming + progress check (Mai Chi, not committed yet)

**New from teammates since 2026-11-18:**
- Thuận Minh: `ml/face_recognition/01_train_classification.ipynb`, `02_train_triplet.ipynb`,
  `03_evaluate_verification.ipynb`. Selected model: triplet + cosine, threshold ≥ 0.5254, holdout AUC 0.954,
  TAR 54.1 % at FAR 2.0 %. Inference code is now `ml/face_recognition/infer.py` and the weights are in `ml/face_recognition/` (see 2026-11-22).
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
