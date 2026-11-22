"""Inference API of presence verification + door audit, for the backend.  Owner: Đức Mạnh

Same convention as ml/<feature>/infer.py: this file plus the model file next to it
(presence_verification.joblib, made by train.py, not in git). Override the path with
HAWKEYE_PRESENCE_VERIFICATION_WEIGHTS. Heavy libraries load on first use.

    to_map(cam_id, box)                       -> (x, y) on the Room 204 map, or None
    audit_door(check_ins, points)             -> {"check_ins", "crossings", "matches", "alerts", "suppressed"}
    score_session(session, check_ins, points) -> [{"student_id", "score", "flagged", "reasons", "rules", "features"}]
    analyze_take(take)                        -> everything above for a recorded take (data/tracks/take<N>/)
    model_info()                              -> what was trained, when, and how well

Shapes (API contract: add fields, never rename):
    check_ins: [{"t": s, "student_id": str, "similarity"?: float, "spoof_flags"?: int}]
    points:    [{"t": s, "track_id": str, "cam_id": "cam_1"|"cam_2", "x": 0..1, "y": 0..1}]   (map positions)
    session:   {"duration": s}
"""
import os
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:          # the helper modules sit next to this file
    sys.path.insert(0, str(HERE))

_lock = threading.Lock()
_state = {}


def _model_path():
    return Path(os.environ.get("HAWKEYE_PRESENCE_VERIFICATION_WEIGHTS", HERE / "presence_verification.joblib"))


def _load():
    with _lock:
        if not _state:
            path = _model_path()
            if not path.is_file():
                raise FileNotFoundError(f"{path} not found. Train it: python ml/presence_verification/train.py")
            import joblib
            from door_audit import DtModel
            bundle = joblib.load(path)
            _state.update(bundle=bundle, dt=DtModel.from_dict(bundle["dt_model"]))
        return _state


def to_map(cam_id, box):
    from trajectories import to_map as _to_map
    return _to_map(cam_id, box)


def _door(check_ins, crossings):
    from door_audit import audit
    st = _load()
    door = st["bundle"]["door"]
    mode = door["mode"]
    return audit(check_ins, crossings, st["dt"], door["pair_clf"] if mode == "clf" else None,
                 door[f"u_{mode}"], door.get(f"min_score_{mode}", 0.0))


def audit_door(check_ins, points):
    """Door audit from check-ins and map points (see the module docstring for the shapes)."""
    from door_audit import detect_crossings, trajectories_from_points
    crossings = detect_crossings(trajectories_from_points(points))
    return {"crossings": crossings, **_door(check_ins, crossings)}


def score_session(session, check_ins, points, door_result=None):
    """Presence score of every checked-in student. door_result: audit_door() output (computed if None)."""
    from presence import score_rows, student_rows
    door_result = door_result or audit_door(check_ins, points)
    s = {"duration": float(session["duration"]), "check_ins": check_ins, "crossings": door_result["crossings"],
         "points": points}
    return score_rows(student_rows(s, door_result), _load()["bundle"]["presence"])


def analyze_take(take, trail_step_s=0.5, class_s=None):
    """Door audit + presence scores of a recorded take, plus downsampled map trails for drawing.
    class_s: length of the class the take is scored as the start of (default sessions.CLASS_S, 90 min)."""
    from presence import score_rows, student_rows
    from pv_common import takes
    from sessions import CLASS_S, real_session
    if int(take) not in takes():
        raise FileNotFoundError(f"data/tracks/take{int(take)}/ does not exist")
    s = real_session(int(take), CLASS_S if class_s is None else class_s)
    door = _door(s["check_ins"], s["crossings"])
    students = score_rows(student_rows(s, door), _load()["bundle"]["presence"])
    flagged_tracks = {t for a in door["alerts"] for t in a["track_ids"]}
    flagged_tracks |= {m["track_id"] for m in door["matches"] for st in students
                       if st["flagged"] and st["student_id"] == m["student_id"]}
    trails = []
    for tr in s["trajectories"]:
        tid = f"{tr['cam_id']}:{tr['track_id']}"
        pts, last = [], None
        for p in tr["points"]:
            if last is None or p["t"] - last >= trail_step_s:
                pts.append([p["t"], p["x"], p["y"]])
                last = p["t"]
        trails.append({"track_id": tid, "cam_id": tr["cam_id"], "name": tr.get("name"), "points": pts,
                       "flagged": tid in flagged_tracks})
    return {"take": int(take), "duration": s["recorded_s"], "scored_as_class_s": s["duration"],
            "check_ins": door["check_ins"],
            "crossings": s["crossings"], "matches": door["matches"], "alerts": door["alerts"],
            "suppressed": door["suppressed"], "students": students, "trails": trails, "model": model_info()}


def model_info():
    b = _load()["bundle"]
    return {"file": _model_path().name, "created": b["created"], "quick": b.get("quick", False),
            "door_mode": b["door"]["mode"], "presence_model": b["presence"]["selected"],
            "threshold": b["presence"]["threshold"], "dt_model": b["dt_model"]}
