"""Fill the database from the mock files in data/mock/.

    python -m app.db.seed            # seed only if the database is empty
    python -m app.db.seed --reset    # empty every table and seed again (works while the backend runs)

Sources: roster.json (courses, and students with their course keys), session.json (today's session),
past_sessions.json (earlier sessions), data/video_config.json (cameras). After the first start the database is the
roster: new students come from the Add person page (POST /api/students).
"""
import argparse
import json

from sqlalchemy import text

from ..config import DB_PATH, MOCK_DIR, VIDEO_CONFIG


def event_type(message):
    m = message.lower()
    if "spoof" in m:
        return "spoof"
    if "checked in" in m:
        return "check_in"
    if "entered" in m:
        return "in"
    if "left" in m:
        return "out"
    return "seen"


def _at(date, hhmm):
    return f"{date}T{hhmm}" if hhmm else None


def _add_session(conn, s, students):
    """s: {course_key, room, date, start, end, attendance: [...], events: [...]} (the frontend's session shape)."""
    sid = conn.execute(text(
        "INSERT INTO sessions (course_key, room, start_at, end_at) VALUES (:c, :r, :a, :b) RETURNING id"),
        {"c": s["course_key"], "r": s["room"], "a": _at(s["date"], s["start"]), "b": _at(s["date"], s["end"])}).scalar()
    for a in s.get("attendance", []):
        conn.execute(text(
            "INSERT INTO attendance (session_id, student_id_vn, global_id, check_in_at, entry_at, exit_at, minutes, status)"
            " VALUES (:sid, :st, :g, :ci, :en, :ex, :m, :status)"),
            {"sid": sid, "st": a["student_id_vn"], "g": a.get("global_id"), "ci": _at(s["date"], a.get("check_in")),
             "en": _at(s["date"], a.get("entry")), "ex": _at(s["date"], a.get("exit")), "m": a.get("minutes"),
             "status": a.get("status", "not_seen")})
    for e in s.get("events", []):
        # Mock events from session.json carry no student ID: match the student's name in the text.
        st = e.get("student_id") or next((x["student_id_vn"] for x in students if x["name"] in e["event"]), None)
        conn.execute(text(
            "INSERT INTO events (session_id, at, cam_id, student_id_vn, type, message) VALUES (:sid, :at, :cam, :st, :t, :msg)"),
            {"sid": sid, "at": _at(s["date"], e["time"]), "cam": e["source"], "st": st,
             "t": event_type(e["event"]), "msg": e["event"]})
    return sid


def seed_all(path=None):
    from . import connect
    from .queries import insert_student
    roster = json.loads((MOCK_DIR / "roster.json").read_text(encoding="utf-8"))
    students = roster["students"]
    session = json.loads((MOCK_DIR / "session.json").read_text(encoding="utf-8"))
    past = json.loads((MOCK_DIR / "past_sessions.json").read_text(encoding="utf-8"))["sessions"]
    cfg = json.loads(VIDEO_CONFIG.read_text(encoding="utf-8"))

    with connect(path) as conn:
        for c in roster["courses"]:
            conn.execute(text("INSERT INTO courses VALUES (:key_id, :course_id, :course_name, :session_time, :room)"), c)
        for s in students:
            insert_student(conn, s)
        for p in session.get("placeholder_students", []):
            conn.execute(text("INSERT INTO placeholder_students (name, note) VALUES (:n, :note)"),
                         {"n": p["student_name"], "note": p.get("note")})
        for cam in cfg["cameras"]:
            conn.execute(text("INSERT INTO cameras (cam_id, role) VALUES (:id, :role)"),
                         {"id": cam["cam_id"], "role": cam.get("role") or cam.get("place")})

        today = {**session["session"], "attendance": session["attendance"], "events": session["events"]}
        for s in sorted([*past, today], key=lambda s: (s["date"], s["start"])):   # oldest first -> ids grow with time
            _add_session(conn, s, students)


def reset(path=None):
    """Delete every row (children first), keeping the tables."""
    from . import connect, init_db
    init_db(path, seed=False)
    with connect(path) as conn:
        for table in ["events", "presence_intervals", "attendance", "sessions", "enrollments", "face_embeddings",
                      "placeholder_students", "cameras", "students", "courses"]:
            conn.execute(text(f"DELETE FROM {table}"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="empty every table first")
    args = ap.parse_args()
    from . import init_db
    if args.reset:
        reset()
    print("Seeded" if init_db() else "Already has data (use --reset)", DB_PATH)


if __name__ == "__main__":
    main()
