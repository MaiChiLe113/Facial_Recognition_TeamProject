# Status

Last updated: 2026-11-24. Update this file at the end of every step: change the current state, don't append a diary.

## Branch

All work goes on **`feature/backend-structure`**. Don't create other branches, merge into `main` or push unless the user asks.

## What works now

**Frontend** (Vue 3, `frontend/src/`)
- **Home** (`/`): source switch **Live / Recorded** (+ take menu), kept in the URL (`/?source=recorded&take=N`; old `/demo` and `/live` redirect here).
  - Live: tiles show the MJPEG stream `/api/live/<cam_id>/stream` with server-drawn boxes; the doorway tile lists the real faces from `GET /api/live` (identity / "please register", liveness, emotion). "+" on an idle tile opens `/camera?cam=<id>`. **Remove** on a live tile (also while sending) calls `POST /api/live/{cam_id}/remove`: the backend closes that sender's WebSocket with code 4001 (the Camera page stops, no reconnect) and the tile goes back to the idle 16:9 size. **QR** button (left of Live) shows a QR of `host_urls[0]` so a phone can scan the Camera page. Event log and map are blank in Live (no live event feed / map positions yet).
  - Recorded: Play / Pause / Restart, synced playback line with scrubbing, event log following the video, presence verification panel, map trails up to the playback position (empty before Play and after a take change), takes table.
  - Room map (`RoomMap.vue`, layout from FigJam in `roomLayout.js`): one object per person (P1, P2…), not per camera: presence-verification trails with the same name are merged across cam_1 / cam_2 (points within 0.4 s averaged); unnamed tracks stay separate until the matcher gives cross-camera IDs. Dot hidden 2 s after the person's last point; legend shows colour, P-number, name, merged camera tracks; red ring = alert.
- Home **Class roster** status comes from the cameras (`rosterStatus.js`), demo only, never saved to the DB: everyone starts Not seen; check-in = the attendance camera recognised them (Recorded: track `name_from` up to the playback position; Live: a live, named face in `GET /api/live`); In class / Left / entry / exit / duration from cam_2 (Recorded: named cam_2 tracks; Live: recognised on cam_2, Left after 30 s unseen). Live state is kept in the page until reload.
- **History** (`/history`): past sessions, roster per session, editable Attended/Status (saved via PATCH).
- **Features demo** (`/features-demo`): webcam → face recognition / anti-spoofing / emotion, threshold sliders (per browser, `localStorage`), session log optionally saved to `logs/features_demo_<time>.csv`.
- **Add person** (`/add`): form + 1–20 photos → `POST /api/students`.
- **Camera** (`/camera`, full screen, phones): sends JPEG frames over `WS /ws/camera/{cam_id}`.
- **System log** (`/system`, gear icon under Features demo): each inference model's version label (`ml/model_versions.json`), last modified time, size, SHA-256, and the change history in `logs/model_changes.jsonl`.
- **Wi-Fi demo guide** (`/guide/lan`): renders `docs/LAN_DEMO.md` with `marked` (`?raw` import, hot-reloads in dev).
- Sidebar is icon-only (72 px; labels as tooltips / aria-labels), so the cameras get more width.
- Styles: one type scale (22/17/15/14/13/12), spacing tokens `--space-1..5`, every colour a `:root` token.

**Backend** (FastAPI, `backend/app/`)
- SQLite `data/hawkeye.sqlite3` is the roster and session store, seeded from `data/mock/roster.json`, `session.json`, `past_sessions.json`. Re-seed: `cd backend && python -m app.db.seed --reset`.
- Live mode: **every camera runs the three face models** (detect faces → liveness → recognise → emotion, always on, set in `pipeline.json`; cam_1 / cam_2 also track people). Only the attendance camera emits `check_in` (`stages/emit.py`); corridor / classroom results are shown on the tiles, not logged. Emotion smoothing is per camera (the `emotion` stage averages 1 s itself, `predict(smooth=False)`); liveness keeps one buffer per camera. `app/api/live.py` + `services/live.py` run `engine.process_frame` on frames from phones; `npm run dev:lan` serves https on the host IP (mkcert cert in `frontend/certs/` if present).
- `pipeline/detector.py` (YOLO11n people, YuNet faces) and `pipeline/tracker.py` (BYTETracker, 3 s buffer) are implemented; `matcher.py` (`GlobalMatcher`) is still a stub.
- `services/gallery.py` owns the registered faces (Drive enrolment photos + uploads), cached in `data/raw/face_embeddings.npz`, kept in `engine.shared["gallery"]`.
- `core/ml_models.py`: `MARGIN` per model (recognition 0.1, anti-spoofing 0.25, emotion 0.0) and `crop_face()`, shared by the Features demo and the attendance-camera stages.
- Presence verification plug-in: `GET /api/features/presence_verification/take/{take}`, `/model`, `/live` (needs `presence_verification.joblib`, rebuild with `ml/presence_verification/train.py`).

**Models** (`ml/<feature>/infer.py` + `<feature>.pt`, loaded through `core/ml_models.py`)
- Face recognition: triplet + cosine, threshold 0.5254 (in the checkpoint), holdout AUC 0.954.
- Anti-spoofing: MobileNetV2, threshold 0.0239; not yet tried on printed photos / phone screens.
- Emotion: ResNet-18 on FER2013 + AffectNet; FER2013 test acc 0.707, AffectNet 0.661.
- Presence verification + door audit (Đức Mạnh's innovation): `ml/presence_verification/` (README, PLAN, TEST, 19 unit tests).
- Tracks precomputed for takes 1–8 in `data/tracks/take<N>/` (YOLO11n + ByteTrack, names by door handoff).

**Tests:** `backend/tests/` (unittest), 50 of 51 pass; `test_every_camera_processes_a_frame` fails only when `ultralytics` is missing from the venv. `npm run build` passes.

## Open issues

- Recognition on doorway frames is weak: take 1 confuses Thuận Minh / Hồng Minh, Đức Mạnh named on 2 of 41 frames; the OpenCV baseline (`name_tracks.py`) named all four correctly on takes 1 and 3.
- Take 3 gives D3 + D1 alerts because the tracker switches IDs when three people stand in the doorway.
- Room 204 map is not measured (`room204_map.json` sizes and `scale_per_m` are estimates), so hand-clicked homographies cannot fit everything. cam_2 v4 (forced Chi's take-1 seat onto the drawn ATT desk) was tried and reverted to v3 on 2026-11-24 after GeoCalib agreed with v3; v4 is only in git history.
- GeoCalib check (2026-11-24, `pip install git+https://github.com/cvg/GeoCalib` in `.venv`): cam_2 f 728 ± 84 px, pitch +4.7° ± 1.1, roll −0.2°; cam_1 f 946 ± 212 px (unreliable), pitch −0.2°. Aligned to the 3 door points with a free scale, it puts cam_2 at (0.746, 0.804), matching the map, but needs a 1.32 scale factor (`scale_per_m` or the 0.83 m camera height is off) and puts Chi's take-1 seat at (0.52, 0.59), agreeing with hand calibration v3, not with the desk rows drawn in the map. The drawn desks were wrong, not the camera: on 2026-11-24 the 8 long desks and attendance_cam were moved up by 0.0954 in `room204_map.json`, so the ATT desk covers y 0.565–0.635.
- **ArUco floor calibration done (2026-11-25), replaces the hand fits above:** `ml/aruco/` (tape survey + 7 printed markers; leave-one-out cam_1 2-9 cm, cam_2 20-60 cm). Presence model not retrained since.
- All recorded takes are normal behaviour; scripted fraud takes still to record.
- Tracking: no MOT metrics yet (only take 3 ground truth checked); no cross-camera Re-ID (`GlobalMatcher` stub); YOLO not fine-tuned.
- Embeddings are not in the `face_embeddings` table (it lacks the file key the cache needs).

## TODOs in code

- `core/stages/attendance_cam.py`: liveness keeps one crop buffer for the main face; needs one per global ID once the matcher links faces to tracks.
- `core/subscribers.py`: `AttendanceLog` should publish `in` / `out` events back onto the bus.
- `main.py`: `/ws/dashboard` not built.
- Live mode has no event feed and no map positions for the frontend.
- The shared design doc still says "React + Vite" / `Home.jsx`.
