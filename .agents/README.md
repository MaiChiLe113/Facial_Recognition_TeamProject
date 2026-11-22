# Notes for AI agents working on Hawkeye

Start here. These files tell an agent (Claude, Copilot, Cursor…) what the project is, what is done, and the rules to follow. Keep them up to date when you finish a step.

| File | Read it for |
| --- | --- |
| `README.md` (this file) | Project in one minute, hard rules, how to run and verify |
| [`assignment.md`](assignment.md) | The full official assignment brief and marking scheme (source of truth for requirements) |
| [`status.md`](status.md) | Branches, what is done, what comes next |
| [`architecture.md`](architecture.md) | How the backend pipeline and the frontend are put together |
| [`decisions.md`](decisions.md) | Decisions already made and why. Do not reopen them without asking |

## The project in one minute

Hawkeye is a COS30082 (Applied Machine Learning) team project: a multi-camera classroom attendance system.

- **Cameras:** three cameras, `cam_1` (corridor), `cam_2` (classroom) and `attendance_cam` (doorway).
- **Global ID:** every tracked person gets a numeric global ID straight away.
- **Recognition:** only the attendance camera recognises faces. It checks liveness, identity and emotion, then the label becomes `ID 7 · Manh` on every camera.
- **Logging:** the system logs check-in, entry, exit and total time in class.

The stack runs locally:
- Backend: FastAPI (Python 3.10+) in `backend/`.
- Frontend: Vue 3 + Vite (npm) in `frontend/`.
- Database: SQLite planned (`backend/app/db/schema.sql`), on hold; data lives in CSV under `data/mock/` for now.

The team design doc is the source of truth for scope and marking. It is a Claude Docs document named "Project Plan" (tabs: Project Brief, Tasks and Codebase, Meeting Notes, Chi document). Ask the user for the link if you need it.

## Hard rules

1. **Ownership.** Only edit files the current user owns. The user is Đức Mạnh, who owns:
   - `frontend/`
   - `backend/app/main.py`, `backend/app/api/`, `backend/app/services/`, `backend/app/core/`
   - `backend/app/db/`
   - `backend/app/pipeline/attendance.py` (shared with Mai Chi)

   Never edit:
   - `backend/app/pipeline/{detector,tracker,matcher}.py` (Mai Chi)
   - `ml/face_recognition/` (Thuận Minh), `ml/anti_spoofing/` (Hồng Minh), `ml/emotion/` (Minh Thành): each holds `infer.py` and the weights `<feature>.pt`; the app finds them through `backend/app/core/ml_models.py`
   - anything else in `ml/`
   - never create a `runs/` folder outside `ml/`

   Shared files (`README.md`, `requirements.txt`, `data/`) need a reason, and the change must stay minimal.
2. **API contract.** Never rename or remove fields in an existing API response; only add. The frontend and teammates depend on the shapes. The bounding-box contract is in the root `README.md`.
3. **Offline fallback.** `frontend/src/api.js` must keep working with the backend down: it builds the same shapes from `data/mock/`.
4. **Never commit** videos, model weights, `.env` or `*.sqlite3` (already in `.gitignore`).
5. **Small steps.** After each step: run it, show the user what changed, and wait for their OK before the next one. Make one git commit per step with a clear message.
6. **Commit messages carry no AI attribution.** No `Co-Authored-By: Claude…` lines, no "Generated with" footers.
7. **Code style.** Code comments and docs are in English (the team's choice). Stage and feature code must import heavy libraries (torch, cv2) inside `setup()`.

## Run and verify

The local machine is Windows. Use the Git Bash or PowerShell tools; paths below are from the repo root.

```bash
# backend (venv lives in backend/.venv, git-ignored)
cd backend
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
.venv/Scripts/python -m unittest discover -s tests -t .      # core isolation tests

# frontend
cd frontend && npm install && npm run dev      # http://localhost:5173
npm run build                                  # quick compile check
```

How to check a backend change does not break the contract:
1. Before the change, save the status and body of every route.
2. After the change, save them again and diff the two sets.
3. Only additions are allowed.

The routes: `/`, `/api/health`, `/api/dashboard`, `/api/demo/config`, `/api/tracks/{cam}` and `/videos/{cam}`. A `404` from `/videos/*` is expected when `HAWKEYE_VIDEO_ROOT` is not set.

Gotchas:
- **Git Bash mangles arguments.** Arguments that start with `/` get rewritten (for example `/api/x` becomes `C:/Program Files/Git/api/x`). Use full URLs, or do HTTP checks from Python.
- **Pylance "fastapi could not be resolved"** only means the editor is not using `backend/.venv`.
- **Demo videos are not in the repo.** They live in the team Google Drive (`AppliedML/video data/`), set through `HAWKEYE_VIDEO_ROOT` in `backend/.env`.

After any code changes, you have to update the .agents/ where needed or be affected by that change(s) to prevent context drift