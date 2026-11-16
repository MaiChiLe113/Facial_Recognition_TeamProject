# Features

One folder per individual innovation feature. A feature reacts to pipeline events and can add its own API routes. It never edits another person's module. If it breaks, only that feature stops.

## Add a feature in 4 steps

1. Copy `event_counter/` to `app/features/<your_feature>/`.
2. Change the name in `@register_feature("<your_feature>")`. The name must be unique.
3. In `setup(self, bus)`, subscribe to the events you need:

   ```python
   bus.subscribe("spoof", self.on_spoof, owner=self.name)
   ```

4. Switch it on in `backend/pipeline.json`:

   ```json
   "features": { "<your_feature>": true }
   ```

   Pass options instead of `true` if you need them: `{ "chat_id": "..." }`. They arrive in `self.options`.

Restart the backend, then open `GET /api/pipeline/status` and check that your feature shows `"status": "ready"`.

## What a feature can use

| You want to | Use |
| --- | --- |
| React to something happening | `bus.subscribe(<type>, handler, owner=self.name)`. Types: `seen`, `check_in`, `spoof`, `in`, `out`, or `"*"` for all |
| Publish your own event | `self.engine.bus.publish(Event("alert", cam_id, t, data={...}))` (`from app.core.types import Event`) |
| Offer HTTP routes | Set `router = APIRouter()` on the class. Routes appear under `/api/features/<name>/` |
| Show state on the status page | Return a dict from `info()` |
| Read shared objects | `self.engine.shared`, e.g. `["matcher"]` or `["attendance"]` |

An event carries `type`, `cam_id`, `t`, `global_id`, `student_id` and `data` (see `app/core/types.py`).

## Add a pipeline stage instead

Use a stage when your work must run on every frame, such as a mask or glasses check on the face crop. Use a feature when you only react to results.

1. Add `app/core/stages/<name>.py` with a class marked `@register_stage("<name>")` (see `app/core/stages/base.py` for the rules).
2. Add the name to the camera role in `backend/pipeline.json`, e.g. `"attendance": [..., "emotion", "<name>", "emit_events"]`.

Write your results to `ctx.extras["<name>"]` or to new keys on a face, and keep the existing fields as they are.

## Rules

- Import heavy libraries (torch, cv2) inside `setup()`, so a missing library only disables your part.
- While a model is not ready, raise `NotImplementedError`. It shows as `not_ready`, not as an error.
- Do not change the JSON shape of existing API routes. Add new routes under your feature instead.
- Run the tests before a pull request: `python -m unittest discover -s tests -t .` from `backend/`.
