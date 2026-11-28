# Decisions

Newest first. Add a line when the user decides something; do not reopen a decision without asking.

| Date | Decision | Why |
| --- | --- | --- |
| 2026-11-28 | Anti-spoofing v1 is kept, moved from the repo root to `ml/anti_spoofing/anti_spoofing_v1.pt` | User request: keep v1 |
| 2026-11-28 | The app runs anti-spoofing v2 (threshold 0.4), copied over `anti_spoofing.pt` | User request |
| 2026-11-28 | In-app Wi-Fi guide page (`/guide/lan`) removed; `docs/LAN_DEMO.md` stays. Replaces that part of the 2026-11-24 decision | User request |
| 2026-11-28 | `own_data/` and `test_out/` (liveness notebook outputs) removed from the repo | User request |
| 2026-11-28 | Home (Recorded) plays only the take set in `data/video_config.json` (commit `a86b692`). Replaces "plays every take" (2026-11-17) | Noted while merging that commit |
| 2026-11-28 | One root requirements file: `requirements.txt` (version ranges). `requirements.lock.txt` removed (exact pins are in Git history). The `ml/*/requirements.txt` files stay | User request |
| 2026-11-28 | Presence verification + door audit removed completely; only the 2D live tracking map stays (projection moved to `backend/app/services/floor_map.py`). Replaces the earlier presence verification decisions below | User request |
| 2026-11-28 | Module `ml/face_quality` renamed to `ml/live_face_scan` (folder, feature key, weights file; model unchanged). Drive folder `face_quality_colab/`, `data/raw/face_quality/` and experiment output names keep the old name | User request |
| 2026-11-26 | `live_face_scan` v2 = the 06_backbones MobileNetV3 winner (Kaggle + team photos + recorded-video faces), threshold 0.58 from the checkpoint; bigger backbones not used | Best on held-out real faces ≥ 80 px (pAUC 32.21 vs v1 35.95), equal on photos, fastest; user approved |
| 2026-11-26 | Đức Mạnh's innovative feature is now the AI enrolment scan + face-quality model (`ml/live_face_scan/`); presence verification becomes a team feature. No face restoration for gallery photos. Quality labels come from `face_recognition` v1, and the quality model is pinned to that version | User request; restoration invents detail and shifts embeddings |
| 2026-11-26 | (v1 only, superseded by v2) The scan used 0.65 for webcam frames, not the checkpoint's 0.78 | At 0.78 only 3 of 27 real webcam frames passed |
| 2026-11-24 | Attend Course page dropped; the Wi-Fi guide is shown in the app (`/guide/lan`) from `docs/LAN_DEMO.md`; anyone may edit any file (ownership rule removed) | User request |
| 2026-11-23 | `scikit-learn`, `scipy`, `joblib` added to `requirements.txt` for presence verification; `*.joblib` and `ml/presence_verification/outputs/` git-ignored. Recorded takes are scored as the start of a 90-min class (`sessions.CLASS_S`) | User asked to implement the plan without waiting for review; team still to be told about the new deps |
| 2026-11-23 | Đức Mạnh's innovative feature = door audit (check-ins vs door crossings) + presence verification, built in `ml/presence_verification/` (plan: its `PLAN.md`); door audit first, presence verification builds on its matches. It reads `data/tracks/` and `link_names.py` output, never writes them | User request (Đức Mạnh) |
| 2026-11-18 | SQLite is the data store (`data/hawkeye.sqlite3`, git-ignored, seeded from `data/mock/`); `data/mock/` stays as seed data and the frontend's offline fallback | User request (Đức Mạnh) |
| 2026-11-17 | Old take 1 deleted (failed recording); takes renumbered 1–8, demo take 4 → 3 | User request (Mai Chi) |
| 2026-11-17 | Boxes are precomputed per take in `data/tracks/take<N>/` and committed; Home (Recorded) plays every take | The demo needs them; small JSON files |
| 2026-11-17 | A name is assigned only at check-in (attendance camera) and carried to cam_1 / cam_2 by a door handoff; the label shows it from `name_from` | Matches the design: recognition only on the attendance camera |
| 2026-11-17 | No video upload in the frontend ("Load from computer" removed) | User request (Mai Chi) |
| 2026-11-16 | Work on a single branch, `feature/backend-structure`; never merge into `main` or push unless asked | User request |
| 2026-11-16 | No AI co-author or "Generated with" lines in commit messages | User request |
| 2026-11-16 | Agent notes live in `.agents/` | User request: future agents follow what is going on |
| 2026-11-16 | Pipeline runner and stage adapters live in `app/core/`, not `app/pipeline/` | Keeps the model files separate from the plumbing |
| 2026-11-16 | Backend pipeline config is JSON (`backend/pipeline.json`), not YAML | No new dependency |
| 2026-11-16 | Tests use stdlib `unittest` (`backend/tests/`) | No new dependency |
| 2026-11-16 | Features are off unless enabled in `pipeline.json`; a failing part is skipped and reported, never fatal | One member's feature must not break the others |
| 2026-11-16 | Frontend is Vue 3 + Vite + Vue Router 4, installed with npm (replaces React) | User request. Router 4 because Router 5 needs Vite 7 and the repo is on Vite 5 |
| 2026-11-16 | README updates stay minimal and factual; the shared design doc is not edited by agents | Team document |
| (template) | FastAPI backend, SQLite via SQLAlchemy, mock data behind the same JSON shapes | Team design doc |
