# Status

Last updated: 2026-11-16. Update this file at the end of every step.

## Branch

All work happens on **one branch: `feature/backend-structure`**. It holds the Vue migration, the backend restructure and this `.agents/` folder. Commit every step there.

- Do not create other branches.
- Do not merge into `main` or push unless the user asks.
- `main` stays as the original template (React frontend, single `main.py`).

## Task list from the user (in order)

| # | Task | State |
| --- | --- | --- |
| 0a | Frontend: React → Vue 3 + npm | Done |
| 0b | Backend: scalable structure, features plug into the pipeline without breaking others | Done |
| 1 | SQLite with SQLAlchemy from `backend/app/db/schema.sql`; seed script for `data/mock/students.csv` and `courses.csv` (a `courses` value like `"[1,2]"` becomes `enrollments` rows); `GET /api/dashboard` reads students and courses from the DB while attendance, events and map still come from `data/mock/session.json` | **Next.** Plan approved in principle, not started |
| 2 | Add person page + `POST /api/students`: name, Student ID (VN, e.g. `SWH02701`), Student ID (AU), year, course checkboxes, 10–20 photos saved to `data/photos/<student_id_vn>/` (git-ignored). Leave a TODO where `recognizer.embed` computes embeddings; do not implement embeddings | Not started |
| 3 | Class page: course table per session (name, student ID, status, check-in, entry, exit, total time, "Logs" link to that student's events); reuse `ClassRoster` | Not started |
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
