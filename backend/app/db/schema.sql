-- Hawkeye SQLite schema (design doc section 6). Owner: Đức Mạnh
-- Created by app/db/__init__.py (init_db) and filled by app/db/seed.py from data/mock/.
-- Times are local ISO text: "2026-11-18T08:31".

CREATE TABLE IF NOT EXISTS students (
  student_id_vn TEXT PRIMARY KEY,      -- e.g. SWH02378
  student_id_au TEXT,
  name          TEXT NOT NULL,
  year          TEXT,
  photo_folder  TEXT,
  student_card  TEXT,                  -- path of the scanned student ID card (also an enrolment face)
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

-- People seen in class who are not in the metadata sheet yet (no student ID).
CREATE TABLE IF NOT EXISTS placeholder_students (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  note TEXT
);

CREATE TABLE IF NOT EXISTS face_embeddings (
  id            INTEGER PRIMARY KEY,
  student_id_vn TEXT REFERENCES students(student_id_vn),
  vector        BLOB NOT NULL,         -- 512 float32
  model_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
  key_id       INTEGER PRIMARY KEY,
  course_id    TEXT NOT NULL,          -- e.g. COS30082
  course_name  TEXT,
  session_time TEXT,
  room         TEXT
);

CREATE TABLE IF NOT EXISTS enrollments (
  student_id_vn TEXT REFERENCES students(student_id_vn) ON DELETE CASCADE,
  course_key    INTEGER REFERENCES courses(key_id) ON DELETE CASCADE,
  PRIMARY KEY (student_id_vn, course_key)
);

CREATE TABLE IF NOT EXISTS sessions (
  id         INTEGER PRIMARY KEY,
  course_key INTEGER REFERENCES courses(key_id),
  room       TEXT,
  start_at   TEXT,
  end_at     TEXT
);

CREATE TABLE IF NOT EXISTS cameras (
  cam_id     TEXT PRIMARY KEY,         -- cam_1, cam_2, attendance_cam
  role       TEXT,                     -- outside / inside / attendance
  stream_url TEXT,
  homography TEXT                      -- 3x3 matrix as JSON
);

-- One row per student per session. entry/exit/minutes are kept here for the pages;
-- presence_intervals holds the raw in/out periods once the pipeline writes them.
CREATE TABLE IF NOT EXISTS attendance (
  session_id     INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
  student_id_vn  TEXT REFERENCES students(student_id_vn) ON DELETE CASCADE,
  global_id      INTEGER,
  check_in_at    TEXT,
  entry_at       TEXT,
  exit_at        TEXT,
  minutes        INTEGER,
  liveness_score REAL,
  emotion        TEXT,
  status         TEXT,                 -- in_class / left / checked_in / not_seen
  attended       INTEGER,              -- manual override from the History page (1/0); NULL = rule
  PRIMARY KEY (session_id, student_id_vn)
);

CREATE TABLE IF NOT EXISTS presence_intervals (
  id            INTEGER PRIMARY KEY,
  session_id    INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
  student_id_vn TEXT REFERENCES students(student_id_vn),
  global_id     INTEGER,
  in_at         TEXT,
  out_at        TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id            INTEGER PRIMARY KEY,
  session_id    INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
  at            TEXT NOT NULL,
  cam_id        TEXT REFERENCES cameras(cam_id),
  global_id     INTEGER,
  student_id_vn TEXT,                  -- NULL while unknown
  type          TEXT NOT NULL,         -- seen, check_in, spoof, in, out
  message       TEXT,                  -- text shown in the event log
  snapshot_path TEXT
);

CREATE INDEX IF NOT EXISTS events_session ON events(session_id, at);
