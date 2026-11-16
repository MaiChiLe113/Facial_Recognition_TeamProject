# Decisions

Newest first. Add a line when the user decides something; do not reopen a decision without asking.

| Date | Decision | Why |
| --- | --- | --- |
| 2026-11-16 | No AI co-author or "Generated with" lines in commit messages | User request |
| 2026-11-16 | Agent notes live in `.agents/` | User request: future agents follow what is going on |
| 2026-11-16 | SQLite (step 1) comes after the backend restructure, as its own step | Least risk: the restructure was checked to change no response first |
| 2026-11-16 | Pipeline runner and stage adapters live in `app/core/`, not `app/pipeline/` | `pipeline/` holds teammates' model files; adapters call them without editing them |
| 2026-11-16 | Backend pipeline config is JSON (`backend/pipeline.json`), not YAML | No new dependency |
| 2026-11-16 | Tests use stdlib `unittest` (`backend/tests/`) | No new dependency |
| 2026-11-16 | Features are off unless enabled in `pipeline.json`; a failing part is skipped and reported, never fatal | One member's feature must not break the others |
| 2026-11-16 | Frontend and backend work on separate branches from `main` (`feature/vue-frontend`, `feature/backend-structure`) | Independent pull requests; they merge cleanly in either order |
| 2026-11-16 | Frontend is Vue 3 + Vite + Vue Router 4, installed with npm (replaces React) | User request. Router 4 because Router 5 needs Vite 7 and the repo is on Vite 5 |
| 2026-11-16 | README updates stay minimal and factual; the shared design doc is not edited | Shared files need team agreement |
| (template) | FastAPI backend, SQLite via SQLAlchemy, mock data behind the same JSON shapes | Team design doc |
