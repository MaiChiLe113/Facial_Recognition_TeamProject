"""Reads and writes used by the API. Every function returns the JSON shapes the frontend expects
(see the comments at the top of the pages section in frontend/src/api.js)."""
import json

from sqlalchemy import text

from ..config import MOCK_DIR, is_upload
from . import connect

STATUSES = {"in_class", "left", "checked_in", "not_seen"}


def _hhmm(at):
    return at[11:16] if at else None


def _photo(student_id, card, folder):
    """The student's picture: the card, or the first uploaded photo (Drive folders may hold HEIC, so not those)."""
    return f"/photos/{student_id}" if card or is_upload(folder) else None


def list_students(path=None, student_id=None):
    """Every student, or only student_id's row (an empty list if unknown)."""
    where, args = (" WHERE student_id_vn = :s", {"s": student_id}) if student_id else ("", {})
    with connect(path) as conn:
        rows = conn.execute(text(f"SELECT * FROM students{where} ORDER BY name"), args).mappings().all()
        enr = conn.execute(text(f"SELECT student_id_vn, course_key FROM enrollments{where} ORDER BY course_key"),
                           args).all()
    courses = {}
    for st, k in enr:
        courses.setdefault(st, []).append(k)
    return [{"student_id_vn": r["student_id_vn"], "student_id_au": r["student_id_au"], "name": r["name"],
             "year": r["year"], "courses": courses.get(r["student_id_vn"], []), "photo_folder": r["photo_folder"],
             "student_card": r["student_card"],
             "photo": _photo(r["student_id_vn"], r["student_card"], r["photo_folder"])} for r in rows]


def get_student(student_id, path=None):
    return next(iter(list_students(path, student_id)), None)


class AlreadyExists(Exception):
    pass


def create_student(student, path=None):
    """student: {student_id_vn, name, student_id_au, year, courses: [course_key], photo_folder, student_card}.
    Raises AlreadyExists for a taken student_id_vn, ValueError for an unknown course. Returns the saved student."""
    sid = student["student_id_vn"]
    with connect(path) as conn:
        if conn.execute(text("SELECT 1 FROM students WHERE student_id_vn = :s"), {"s": sid}).first():
            raise AlreadyExists(f"{sid} is already registered")
        known = {k for (k,) in conn.execute(text("SELECT key_id FROM courses"))}
        unknown = sorted(set(student.get("courses", [])) - known)
        if unknown:
            raise ValueError(f"unknown course key(s): {unknown}")
        insert_student(conn, student)
    return get_student(sid, path)


def insert_student(conn, student):
    """One students row plus its enrollments (used by create_student and by the seed)."""
    conn.execute(text(
        "INSERT INTO students (student_id_vn, student_id_au, name, year, photo_folder, student_card)"
        " VALUES (:vn, :au, :name, :year, :folder, :card)"),
        {"vn": student["student_id_vn"], "au": student.get("student_id_au") or None, "name": student["name"],
         "year": student.get("year") or None, "folder": student.get("photo_folder") or None,
         "card": student.get("student_card") or None})
    for k in sorted(set(student.get("courses", []))):
        conn.execute(text("INSERT INTO enrollments VALUES (:st, :k)"), {"st": student["student_id_vn"], "k": k})


def list_courses(path=None):
    with connect(path) as conn:
        return [dict(r) for r in conn.execute(text("SELECT * FROM courses ORDER BY key_id")).mappings()]


def _attendance_row(a):
    return {"student_id_vn": a["student_id_vn"], "global_id": a["global_id"], "status": a["status"] or "not_seen",
            "check_in": _hhmm(a["check_in_at"]), "entry": _hhmm(a["entry_at"]), "exit": _hhmm(a["exit_at"]),
            "minutes": a["minutes"], "attended": None if a["attended"] is None else bool(a["attended"])}


def list_sessions(path=None):
    """All sessions, newest first, each with its attendance rows and events (newest first)."""
    with connect(path) as conn:
        sessions = conn.execute(text("SELECT * FROM sessions ORDER BY start_at DESC")).mappings().all()
        att = conn.execute(text("SELECT * FROM attendance")).mappings().all()
        events = conn.execute(text("SELECT * FROM events ORDER BY at DESC, id DESC")).mappings().all()
    out = []
    for s in sessions:
        out.append({
            "id": s["id"], "course_key": s["course_key"], "room": s["room"],
            "date": (s["start_at"] or "")[:10], "start": _hhmm(s["start_at"]), "end": _hhmm(s["end_at"]),
            "attendance": [_attendance_row(a) for a in att if a["session_id"] == s["id"]],
            "events": [{"time": _hhmm(e["at"]), "event": e["message"], "source": e["cam_id"],
                        "student_id": e["student_id_vn"], "type": e["type"]}
                       for e in events if e["session_id"] == s["id"]],
        })
    return out


def update_attendance(session_id, student_id, changes, path=None):
    """changes: {"status": ..., "attended": true/false/null}. Creates the row if the student had none."""
    fields = {}
    if "status" in changes:
        if changes["status"] not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        fields["status"] = changes["status"]
    if "attended" in changes:
        a = changes["attended"]
        fields["attended"] = None if a is None else int(bool(a))
    if not fields:
        raise ValueError("nothing to change: send status and/or attended")
    with connect(path) as conn:
        if not conn.execute(text("SELECT 1 FROM sessions WHERE id = :s"), {"s": session_id}).first():
            raise LookupError(f"no session {session_id}")
        if not conn.execute(text("SELECT 1 FROM students WHERE student_id_vn = :st"), {"st": student_id}).first():
            raise LookupError(f"no student {student_id}")
        conn.execute(text("INSERT OR IGNORE INTO attendance (session_id, student_id_vn, status)"
                          " VALUES (:s, :st, 'not_seen')"), {"s": session_id, "st": student_id})
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        conn.execute(text(f"UPDATE attendance SET {sets} WHERE session_id = :s AND student_id_vn = :st"),
                     {**fields, "s": session_id, "st": student_id})
        row = conn.execute(text("SELECT * FROM attendance WHERE session_id = :s AND student_id_vn = :st"),
                           {"s": session_id, "st": student_id}).mappings().one()
    return _attendance_row(row)


def build_dashboard(path=None):
    """Home page: the newest session from the database. The attendance-camera status and the map
    positions are live pipeline state, not records, so they still come from data/mock/session.json."""
    live = json.loads((MOCK_DIR / "session.json").read_text(encoding="utf-8"))
    sessions = list_sessions(path)
    s = sessions[0]
    course = next(c for c in list_courses(path) if c["key_id"] == s["course_key"])
    by_id = {a["student_id_vn"]: a for a in s["attendance"]}

    roster = []
    for st in list_students(path):
        a = by_id.get(st["student_id_vn"], {})
        roster.append({
            "name": st["name"], "student_id": st["student_id_vn"], "global_id": a.get("global_id"),
            "enrolled": s["course_key"] in st["courses"],     # False = course not set in the metadata sheet yet
            "status": a.get("status", "not_seen"), "check_in": a.get("check_in"), "entry": a.get("entry"),
            "exit": a.get("exit"), "minutes": a.get("minutes"), "attended": a.get("attended"), "photo": st["photo"],
        })
    with connect(path) as conn:
        for p in conn.execute(text("SELECT name, note FROM placeholder_students ORDER BY id")).mappings():
            roster.append({"name": p["name"], "student_id": None, "global_id": None, "enrolled": False,
                           "status": "placeholder", "note": p["note"], "check_in": None, "entry": None,
                           "exit": None, "minutes": None, "attended": None, "photo": None})

    return {
        "source": "sqlite",
        "course": {"id": course["course_id"], "name": course["course_name"],
                   "session_time": course["session_time"], "room": s["room"]},
        "session": {"id": s["id"], "course_key": s["course_key"], "room": s["room"],
                    "date": s["date"], "start": s["start"], "end": s["end"]},
        "roster": roster,
        "events": [{"time": e["time"], "event": e["event"], "source": e["source"]} for e in s["events"]],
        "attendance_cam_status": live["attendance_cam_status"],
        "map": live["map"],
    }
