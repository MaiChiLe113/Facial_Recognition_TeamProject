-- Hawkeye SQLite schema (design doc section 6). Not wired yet. Owner: Đức Mạnh

CREATE TABLE students (
  student_id_vn TEXT PRIMARY KEY,      -- e.g. SWH02378
  student_id_au TEXT,
  name          TEXT NOT NULL,
  year          TEXT,
  photo_folder  TEXT,
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE face_embeddings (
  id            INTEGER PRIMARY KEY,
  student_id_vn TEXT REFERENCES students(student_id_vn),
  vector        BLOB NOT NULL,         -- 512 float32
  model_version TEXT NOT NULL
);

CREATE TABLE courses (
  key_id       INTEGER PRIMARY KEY,
  course_id    TEXT NOT NULL,          -- e.g. COS30082
  course_name  TEXT,
  session_time TEXT,
  room         TEXT
);

CREATE TABLE enrollments (
  student_id_vn TEXT REFERENCES students(student_id_vn),
  course_key    INTEGER REFERENCES courses(key_id),
  PRIMARY KEY (student_id_vn, course_key)
);

CREATE TABLE sessions (
  id         INTEGER PRIMARY KEY,
  course_key INTEGER REFERENCES courses(key_id),
  room       TEXT,
  start_at   TEXT,
  end_at     TEXT
);

CREATE TABLE cameras (
  cam_id     TEXT PRIMARY KEY,         -- cam_1, cam_2, attendance_cam
  role       TEXT,                     -- outside / inside / attendance
  stream_url TEXT,
  homography TEXT                      -- 3x3 matrix as JSON
);

CREATE TABLE attendance (
  session_id     INTEGER REFERENCES sessions(id),
  student_id_vn  TEXT REFERENCES students(student_id_vn),
  check_in_at    TEXT,
  liveness_score REAL,
  emotion        TEXT,
  status         TEXT,
  PRIMARY KEY (session_id, student_id_vn)
);

CREATE TABLE presence_intervals (
  id            INTEGER PRIMARY KEY,
  session_id    INTEGER REFERENCES sessions(id),
  student_id_vn TEXT REFERENCES students(student_id_vn),
  global_id     INTEGER,
  in_at         TEXT,
  out_at        TEXT
);

CREATE TABLE events (
  id            INTEGER PRIMARY KEY,
  at            TEXT NOT NULL,
  cam_id        TEXT REFERENCES cameras(cam_id),
  global_id     INTEGER,
  student_id_vn TEXT,                  -- NULL while unknown
  type          TEXT NOT NULL,         -- seen, check_in, spoof, in, out
  snapshot_path TEXT
);
