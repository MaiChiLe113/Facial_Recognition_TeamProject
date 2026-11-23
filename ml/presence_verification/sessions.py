"""A recorded take as a session (same shape as simulate.py's), plus the real dt samples.  Owner: Đức Mạnh"""
from door_audit import detect_crossings
from pv_common import check_ins_from_tracks, load_ground_truth, load_tracks, takes
from trajectories import flat_points, take_trajectories


def take_duration(take):
    ends = [k["t"] for cam in ("cam_1", "cam_2", "attendance_cam") for tr in load_tracks(take, cam)
            for k in tr.get("keyframes", [])[-1:]]
    return max(ends, default=0.0)


CLASS_S = 5400.0     # a recorded take is scored as the first seconds of a 90-minute class


def real_session(take, class_s=CLASS_S):
    """A recorded take as a session. The takes only film people arriving, so presence is scored as if the
    class went on for class_s after the recording started (None = the take length): whoever was not seen
    walking out is still in class, the same rule as everywhere else. "recorded_s" keeps the real length."""
    traj = take_trajectories(take)
    rec = round(take_duration(take), 2)
    return {"take": take, "duration": max(rec, class_s or 0.0), "recorded_s": rec, "kind": "recorded",
            "check_ins": check_ins_from_tracks(take), "crossings": detect_crossings(traj),
            "points": flat_points(traj), "trajectories": traj}


def real_dt_samples():
    """dt = entry - check-in from the recorded takes.
    - data/ground_truth/take<N>.csv: each person's check_in and enter_class rows (hand-labelled)
    - takes without ground truth: a check-in and the entry crossing of the cam_2 track that link_names.py
      gave the same name (Mai Chi's naming; read only)
    Returns [(take, source, dt)]."""
    out = []
    for take in takes():
        gt = load_ground_truth(take)
        if gt:
            ci = {r["person"]: r["appear_s"] for r in gt if r["event"] == "check_in"}
            for r in gt:
                if r["event"] == "enter_class" and r["person"] in ci:
                    out.append((take, "ground_truth", round(r["appear_s"] - ci[r["person"]], 2)))
            continue
        s = real_session(take)
        names = {f"{t['cam_id']}:{t['track_id']}": t.get("name") for t in s["trajectories"]}
        for c in s["check_ins"]:
            same = [x for x in s["crossings"] if x["direction"] == "in" and names.get(x["track_id"]) == c["student_id"]]
            if same:
                out.append((take, "link_names", round(same[0]["t"] - c["t"], 2)))
    return out
