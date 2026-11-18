# Decisions

Newest first. Add a line when the user decides something; do not reopen a decision without asking.

| Date | Decision | Why |
| --- | --- | --- |
| 2026-11-18 | SQLite is the data store (`data/hawkeye.sqlite3`, git-ignored, seeded from `data/mock/`); CSV/JSON in `data/mock/` stay as seed data and the frontend's offline fallback. Attendance-cam status and map positions stay in `session.json` (live state) | User request (Đức Mạnh); lifts the 2026-11-17 hold |
| 2026-11-17 | Keep CSV (`data/mock/`) as the data store for now; SQLite step 1 on hold | User request (Mai Chi) |
| 2026-11-17 | Old take 1 deleted (failed recording); takes renumbered 1–8, demo take 4 → 3 | User request (Mai Chi) |
| 2026-11-17 | Boxes are precomputed per take in `data/tracks/take<N>/` and committed; the Demo page plays every take | The demo needs them; small JSON files |
| 2026-11-17 | A name is assigned only at check-in (attendance camera) and carried to cam_1 / cam_2 by a door handoff; the label shows it from `name_from` | Matches the design: recognition only on the attendance camera |
| 2026-11-17 | Face naming uses OpenCV YuNet + SFace as a baseline until the trained face model is ready | Needed now for the demo; no training required |
| 2026-11-17 | No video upload in the frontend ("Load from computer" removed) | User request (Mai Chi) |
| 2026-11-16 | Work on a single branch, `feature/backend-structure`; never merge into `main` or push unless asked | User request |
| 2026-11-16 | No AI co-author or "Generated with" lines in commit messages | User request |
| 2026-11-16 | Agent notes live in `.agents/` | User request: future agents follow what is going on |
| 2026-11-16 | SQLite (step 1) comes after the backend restructure, as its own step | Least risk: the restructure was checked to change no response first |
| 2026-11-16 | Pipeline runner and stage adapters live in `app/core/`, not `app/pipeline/` | `pipeline/` holds teammates' model files; adapters call them without editing them |
| 2026-11-16 | Backend pipeline config is JSON (`backend/pipeline.json`), not YAML | No new dependency |
| 2026-11-16 | Tests use stdlib `unittest` (`backend/tests/`) | No new dependency |
| 2026-11-16 | Features are off unless enabled in `pipeline.json`; a failing part is skipped and reported, never fatal | One member's feature must not break the others |
| 2026-11-16 | Frontend is Vue 3 + Vite + Vue Router 4, installed with npm (replaces React) | User request. Router 4 because Router 5 needs Vite 7 and the repo is on Vite 5 |
| 2026-11-16 | README updates stay minimal and factual; the shared design doc is not edited | Shared files need team agreement |
| (template) | FastAPI backend, SQLite via SQLAlchemy, mock data behind the same JSON shapes | Team design doc |
