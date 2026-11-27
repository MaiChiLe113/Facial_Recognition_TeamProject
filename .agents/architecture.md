# Architecture

## Backend (`backend/app/`)

```
main.py            builds the app, includes routers, starts the Engine in the lifespan
api/               one router per area: system, dashboard, demo, pipeline, photos, records, live, features_demo (ROUTERS in __init__.py)
services/          plain functions the routes call (videos, live, gallery, features_demo)
db/__init__.py     SQLite via SQLAlchemy Core: connect(), init_db() (tables from schema.sql; seeds a new DB)
db/schema.sql      SQLite tables
db/seed.py         fills the DB from data/mock/ (python -m app.db.seed [--reset])
db/queries.py      students, courses, sessions, dashboard, update_attendance (frontend JSON shapes)
core/              plug-in pipeline
  types.py         FrameContext (one frame through the stages), Event, EVENT_TYPES
  registry.py      @register_stage(name) / @register_feature(name); duplicate names raise
  discovery.py     imports every module of a package; one failed import is recorded, the rest load
  events.py        EventBus: subscribe(type | "*", handler, owner), publish(event)
  runner.py        CameraPipeline: runs one camera's stage list per frame, isolates failures
  engine.py        Engine: reads backend/pipeline.json, one pipeline per camera, attendance subscriber, features
  features.py      Feature base class + loader
  subscribers.py   connects AttendanceLog (pipeline/attendance.py) to check_in / seen events
  stages/          adapters around the teammates' model files in pipeline/ (the model files stay unchanged)
    people.py          detect_people, track, match   (one shared GlobalMatcher in engine.shared)
    attendance_cam.py  detect_faces, liveness, recognize, emotion
    emit.py            emit_events: frame results -> seen / check_in / spoof events
features/          one folder per innovation feature; event_counter/ is the template; README.md is the guide
pipeline/          detector, tracker (implemented), matcher (stub), attendance
```

`backend/pipeline.json` decides:
- which cameras exist and their role (`outside`, `inside`, `attendance`);
- the ordered stage list per role;
- stage options;
- which features are on. Features are off unless set to `true`.

### Status values

| Status | Meaning |
| --- | --- |
| `pending` | Set up, no frame yet |
| `ready` | Ran fine |
| `not_ready` | The code raised `NotImplementedError` (a stub). Not counted as an error; not called again |
| `failed` | Import or setup error, an unknown name, or 20 errors while running. Skipped from then on |
| `disabled` | A feature that is switched off |

`GET /api/pipeline/status` shows all of them, plus import errors.

If the engine cannot start at all, `app.state.engine` is `None`. The dashboard, demo and tracks routes keep working, and the status route returns the error.

### Frame flow

1. `engine.process_frame(cam_id, image, t)` runs that camera's stages in order. Each stage fills its own fields on `ctx`: `people`, `tracks`, `faces`, or `extras[...]`.
2. `emit_events` turns the results into events.
3. The bus delivers the events to subscribers: the attendance rules and the enabled features.

Live mode calls `process_frame` for every frame a phone sends over `/ws/camera/{cam_id}`.

### Adding things

- **A per-frame step:** a new file in `core/stages/` with `@register_stage("x")`, plus its name in a role in `pipeline.json`.
- **A reaction to events, or new routes:** `features/<name>/` with `@register_feature("<name>")`, plus `"<name>": true` in `pipeline.json`. Feature routes mount at `/api/features/<name>/`.
- **New HTTP area:** `api/<area>.py` with `router = APIRouter()`, added to `ROUTERS` in `api/__init__.py`.

## When someone replaces a model's `.pt` file

Applies to `ml/face_recognition/face_recognition.pt`, `ml/anti_spoofing/anti_spoofing.pt`, `ml/emotion/emotion.pt`, `ml/gesture/gesture.pt`, `ml/face_quality/face_quality.pt` (or the `HAWKEYE_<FEATURE>_WEIGHTS` override). Weights are never committed (see `.gitignore`); teammates copy the file in by hand.

What the app does by itself:
- **Threshold:** face recognition and anti-spoofing keep their decision threshold *inside* the `.pt` (chosen on validation data: ROC / EER). Nothing in the app hard-codes it. The Features demo page shows it as "Model default" (from `GET /api/features-demo/status`, field `threshold`) and logs the value actually used in the CSV (`threshold`, `liveness_threshold`).
- **Face gallery cache:** `data/raw/face_embeddings.npz` is rebuilt automatically when the face recognition `.pt` changes (the cache key is the file size + modified time, see `services/gallery.py`). The first request afterwards re-embeds every enrolment photo, so expect a delay once.

What a person or agent must do:
1. **Keep the contract of `infer.py`.** The app calls `face_recognition.infer.identify()` / `threshold()`, `anti_spoofing.infer.check()` (and reads `infer._load()["threshold"]`, because it has no public accessor), `emotion.infer.predict()` / `reset()`, `gesture.infer.predict()` (whole frame -> list of hands). If the new model needs a different input size, normalisation or crop margin, change it inside `infer.py` or the checkpoint, and update `MARGIN` in `backend/app/core/ml_models.py` if it must change.
2. **Store the threshold in the checkpoint** (`payload["threshold"]` for recognition, `ckpt["threshold"]` for anti-spoofing). Choose it on the DEV/validation split, never on the evaluation split. A checkpoint without it breaks loading.
3. **Tell users to press Reset on the threshold sliders.** A custom threshold is stored in each browser (`localStorage` keys `hawkeye.faceThreshold`, `hawkeye.livenessThreshold`) and survives a model change, but it was tuned for the *old* model. A custom value that suited the old model can be wrong for the new one.
4. **Check on the Features demo page** (`/features-demo`): the feature shows no "weights missing" tag, "Model default" is the number you expect, and a known student is named while a stranger shows "Unknown". For anti-spoofing, also try a printed photo and a phone screen, not only a real face.
5. **Update the numbers written in `.agents/status.md`** (selected model, threshold, AUC) so the next agent does not read stale values, and do not commit the `.pt`.
6. The `recognize` stage option `threshold` in `backend/pipeline.json` is `null` (use the model's own). If someone set a number there for the old model, change it back or re-tune it.

**Face quality** depends on the recogniser: its labels come from `face_recognition` v1. When `face_recognition.pt` changes, re-run `ml/face_quality/01_build_labels.ipynb` → 02 → 03, then bump `face_quality` in `ml/model_versions.json`. The enrolment scan caps its per-session quality bar at the checkpoint's threshold when `threshold_domain` is "webcam" (v2: 0.58), else at `QUALITY_THRESHOLD_WEBCAM` 0.65 (`backend/app/services/enrol.py`, see `FACE_QUALITY.md` §6).

## Model versions (System log page)

The user controls which version of each model the app runs. `ml/model_versions.json` (committed) holds a hand-set
label per model: `{"<key>": {"version": "v2", "note": "what changed"}}`, keys `face_recognition`, `anti_spoofing`,
`emotion`, `presence_verification`, `face_detector`, `person_detector`. The System log page (`/system`, gear icon,
`GET /api/system/models`, `services/model_log.py`) shows, per model, the file the app actually loads (same paths and
`HAWKEYE_*` overrides as the loaders), its version label, last modified time, size and SHA-256 fingerprint. Every change
it detects (new fingerprint or new label) is appended to `logs/model_changes.jsonl` (git-ignored, per machine), checked
at backend startup and on each page load.

Rules for agents:
1. **Never replace, retrain into, rename or delete a model file the app loads unless the user asks for it.**
2. When the user does replace one, bump its `version` in `ml/model_versions.json` and say what changed in `note`, in the same step. Use the label the user gives; otherwise the next `vN`.
3. Keep old versions only if the user asks, as `ml/<feature>/<feature>_<version>.pt` (not loaded by the app; weights are not committed unless they already are).
4. To roll back: put the old file back at the loaded path (or point `HAWKEYE_<FEATURE>_WEIGHTS` at it) and set the label back. The log records it as "file replaced".
5. After a change, open `/system` and check that the fingerprint and label moved, then follow "When someone replaces a model's `.pt` file" above.
6. Adding a model the app infers with: add it to `models()` in `services/model_log.py` and to `ml/model_versions.json`.

"Last modified" is the file date on that machine (a clone or copy resets it); the fingerprint is the reliable identity.

## Presence verification + door audit (`ml/presence_verification/`)

Đức Mạnh's innovative feature. Reads `data/tracks/`, `data/calibration/`, `data/ground_truth/` (never writes them).
Flow: tracks → map points (`trajectories.py`) → door crossings → match check-ins ↔ entries (`door_audit.py`, Hungarian +
pair classifier) → alerts D1/D2/D3 → per-student features + rules R1–R5 + model score (`presence.py`).
Models train on simulated sessions (`simulate.py`) whose parameters come from the recorded takes; `train.py` writes
`presence_verification.joblib`, `evaluate.py` writes `outputs/eval/report.md`. The backend loads `infer.py` from
`backend/app/features/presence_verification/` and serves it under `/api/features/presence_verification/`.
If `data/tracks/` or the homographies change, retrain and re-run `evaluate.py`: the dt model is fitted on the takes.

## Frontend (`frontend/src/`)

```
pages.js           page registry (router + sidebar built from it): Home, History, Features demo, Camera, Add person, Wi-Fi guide
router.js          routes from pages.js + redirects (/class, /demo, /live, unknown -> /)
api.js             fetch helpers with offline fallback to data/mock (keep it working)
pages/             Home, History, FeaturesDemo, AddPerson, Camera, LanGuide, Placeholder
components/        Sidebar, CameraCard, EventLog, ClassRoster, RoomMap, PresencePanel, QrButton
composables/       useSyncedPlayback (Recorded mode: play/seek the three videos together)
roomLayout.js      2D map drawing (from FigJam); takeEvents.js, format.js helpers
styles.css         all global styles; tokens on :root (colours, --space-1..5); no UI library
```

To add a page, add one entry in `pages.js`. Vite proxies `/api`, `/videos`, `/photos` and `/ws` to the backend (`HAWKEYE_BACKEND`, default `:8000`).

## Data contracts

- **Dashboard:** `GET /api/dashboard` returns `{source, course, session, roster[], events[], attendance_cam_status, map}`. `api.js` `buildMockDashboard()` builds the same shape offline.
- **Boxes:** `GET /api/tracks/{cam_id}?take=N` returns `{cam_id, source, tracks:[{global_id, name, keyframes:[{t, box:[x,y,w,h]}]}]}`, with each box as fractions 0–1 of the frame and `t` in seconds of that camera's video. Optional per-track fields: `name_from` (show `name` from this time on) and `name_source`. The data comes from `data/tracks/take<N>/`; for the default take, `data/tracks/<cam>.json` and then `data/mock/tracks/` are fallbacks.
- **Demo:** `GET /api/demo/config?take=N` returns `{take, default_take, cameras:[{..., file, available, url}]}`; `url` is `/videos/{cam_id}?take=N`.
