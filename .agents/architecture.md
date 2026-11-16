# Architecture

## Backend (`backend/app/`)

```
main.py            builds the app, includes routers, starts the Engine in the lifespan
api/               one router per area: system, dashboard, demo, pipeline (ROUTERS list in __init__.py)
services/          plain functions the routes call (videos.py; dashboard builder moves here with the DB)
mock_store.py      builds /api/dashboard from data/mock/ (to be replaced by DB queries, same JSON)
db/schema.sql      SQLite tables (not wired yet; step 1)
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
pipeline/          teammates' model stubs (do not edit, see .agents/README.md)
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

Nothing calls `process_frame` yet. The camera WebSocket (step 5) or a demo runner will.

### Adding things

- **A per-frame step:** a new file in `core/stages/` with `@register_stage("x")`, plus its name in a role in `pipeline.json`.
- **A reaction to events, or new routes:** `features/<name>/` with `@register_feature("<name>")`, plus `"<name>": true` in `pipeline.json`. Feature routes mount at `/api/features/<name>/`.
- **New HTTP area:** `api/<area>.py` with `router = APIRouter()`, added to `ROUTERS` in `api/__init__.py`.

## Frontend (`frontend/src/`)

```
main.js            createApp(App).use(router)
pages.js           page registry: key, path, label, icon, component (no component -> Placeholder card)
router.js          Vue Router 4 routes built from pages.js (unknown paths redirect to /)
App.vue            sidebar + <RouterView>
api.js             fetch helpers with offline fallback to data/mock (keep it working)
pages/             Home.vue (built), Placeholder.vue
components/        Sidebar, CameraCard (video + canvas box overlay; exposes `video`), EventLog, ClassRoster, RoomMap
styles.css         all styles (plain CSS, no UI library)
```

To add a page, add one entry in `pages.js`. The Vite dev server proxies `/api` and `/videos` to `:8000`. The step 5 WebSocket will also need a proxy entry for `/ws` with `ws: true`.

## Data contracts

- **Dashboard:** `GET /api/dashboard` returns `{source, course, session, roster[], events[], attendance_cam_status, map}`. `api.js` `buildMockDashboard()` builds the same shape offline.
- **Boxes:** `GET /api/tracks/{cam_id}` returns `{cam_id, source, tracks:[{global_id, name, keyframes:[{t, box:[x,y,w,h]}]}]}`, with each box as fractions 0–1 of the frame and `t` in seconds of that camera's video. The data comes from `data/tracks/` if present, else `data/mock/tracks/`.
