"""Builds the dashboard from the mock files in data/mock/.

Swap this module for real database queries once backend/app/db is wired up.
The frontend only depends on the JSON shape returned by build_dashboard().
"""
import csv
import json

from .config import MOCK_DIR


def _read_csv(name):
    with open(MOCK_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _parse_courses(value):
    value = (value or "").strip().strip("[]")
    return [int(v) for v in value.split(",") if v.strip()]


def build_dashboard():
    students = _read_csv("students.csv")
    courses = {int(c["key_id"]): c for c in _read_csv("courses.csv")}
    session = json.loads((MOCK_DIR / "session.json").read_text(encoding="utf-8"))

    course = courses[session["session"]["course_key"]]
    by_id = {a["student_id_vn"]: a for a in session["attendance"]}

    roster = []
    for s in students:
        a = by_id.get(s["student_id_vn"], {})
        enrolled = session["session"]["course_key"] in _parse_courses(s["courses"])
        roster.append({
            "name": s["student_name"],
            "student_id": s["student_id_vn"],
            "global_id": a.get("global_id"),
            "enrolled": enrolled,                 # False = course not set in the metadata sheet yet
            "status": a.get("status", "not_seen"),
            "check_in": a.get("check_in"),
            "entry": a.get("entry"),
            "exit": a.get("exit"),
            "minutes": a.get("minutes"),
            "photo": None,                        # TODO: first photo from s["photo_folder"]
        })
    for p in session.get("placeholder_students", []):
        roster.append({"name": p["student_name"], "student_id": None, "global_id": None,
                       "enrolled": False, "status": "placeholder", "note": p["note"],
                       "check_in": None, "entry": None, "exit": None, "minutes": None, "photo": None})

    return {
        "source": "mock",
        "course": {"id": course["course_id"], "name": course["course_name"],
                   "session_time": course["session_time"], "room": session["session"]["room"]},
        "session": session["session"],
        "roster": roster,
        "events": session["events"],
        "attendance_cam_status": session["attendance_cam_status"],
        "map": session["map"],
    }
