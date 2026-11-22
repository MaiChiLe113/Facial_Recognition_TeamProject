"""Presence verification: did a student who checked in actually stay in class?  Owner: Đức Mạnh

Per student x session: a feature vector (FEATURES), the rules R1-R5 (each gives a reason in words) and a
model score (IsolationForest or a supervised classifier, chosen in train.py).

Identity in the room comes from the door audit: the check-in is matched to the entry crossing, and that
crossing's track is the student's track. A track that simply disappears inside the room (occlusion, the
tracker losing someone who sits down) does NOT mean the student left: a student is in the room from the
entry until an exit crossing of one of their tracks, or until the end of the session.
"""
import math

import numpy as np

from pv_common import metres_per_unit

FEATURES = ["checkin_offset_ratio", "n_checkins", "door_match_cost", "door_to_room_s", "time_in_room_ratio",
            "n_exits", "left_early_ratio", "max_speed", "seat_stability", "n_name_conflicts", "n_spoof_flags",
            "recog_similarity"]
GROUPS = {   # for the ablation in evaluate.py
    "time": ["checkin_offset_ratio", "time_in_room_ratio", "n_exits", "left_early_ratio"],
    "space": ["max_speed", "seat_stability", "n_name_conflicts"],
    "recognition": ["n_checkins", "n_spoof_flags", "recog_similarity"],
    "door_audit": ["door_match_cost", "door_to_room_s"],
}
RULES = {                       # thresholds of the rules (the report justifies each one)
    "R2_min_ratio": 0.5,        # in class for less than half of the time after check-in
    "R3_max_speed": 4.0,        # m/s: faster than running between two map points = two places at once
    "R5_left_early": 0.2,       # left for good with more than 20 % of the session still to go
}
CAP_DOOR_S = 60.0               # door_to_room_s when the student never entered
CAP_COST = 20.0                 # door_match_cost when unmatched
SPEED_MIN_DT = 1.0              # speed is measured over steps of at least 1 s (smooths homography jitter)
CONFLICT_M = 1.5                # two tracks of one student further apart than this at the same time = conflict


def _union_length(intervals):
    total, cur = 0.0, None
    for a, b in sorted(intervals):
        if cur is None or a > cur[1]:
            if cur:
                total += cur[1] - cur[0]
            cur = [a, b]
        else:
            cur[1] = max(cur[1], b)
    return total + (cur[1] - cur[0] if cur else 0.0)


def _metres(dx, dy):
    mx, my = metres_per_unit()
    return math.hypot(dx * mx, dy * my)


def _max_speed(points):
    best, anchor = 0.0, None
    for p in points:
        if anchor is None:
            anchor = p
            continue
        dt = p["t"] - anchor["t"]
        if dt >= SPEED_MIN_DT:
            best = max(best, _metres(p["x"] - anchor["x"], p["y"] - anchor["y"]) / dt)
            anchor = p
    return min(best, 20.0)


def _conflicts(tracks_pts):
    """Number of 1-s bins in which two of the student's tracks are both seen and far apart."""
    bins = {}
    for tid, pts in tracks_pts.items():
        for p in pts:
            bins.setdefault(int(p["t"]), {}).setdefault(tid, []).append((p["x"], p["y"]))
    n = 0
    for per_track in bins.values():
        if len(per_track) < 2:
            continue
        centres = [np.mean(v, axis=0) for v in per_track.values()]
        far = any(_metres(*(centres[i] - centres[j])) > CONFLICT_M
                  for i in range(len(centres)) for j in range(i + 1, len(centres)))
        n += far
    return n


def student_rows(session, door_result):
    """One row per checked-in student: {"student_id", "features": {...}, "rules": [...], "reasons": [...]}."""
    D = float(session["duration"])
    crossings = session.get("crossings", [])
    pts_by_track = {}
    for p in session.get("points", []):
        pts_by_track.setdefault(str(p["track_id"]), []).append(p)
    for v in pts_by_track.values():
        v.sort(key=lambda p: p["t"])
    exits_by_track = {}
    for c in crossings:
        if c["direction"] == "out":
            exits_by_track.setdefault(c["track_id"], []).append(c["t"])

    raw_by_sid = {}
    for c in session.get("check_ins", []):
        raw_by_sid.setdefault(c.get("student_id"), []).append(c)
    merged_by_sid = {}
    for c in door_result["check_ins"]:
        merged_by_sid.setdefault(c.get("student_id"), []).append(c)
    matches_by_sid = {}
    for m in door_result["matches"]:
        matches_by_sid.setdefault(m["student_id"], []).append(m)
    d3 = {a["student_id"] for a in door_result["alerts"] if a["code"] == "D3"}

    rows = []
    for sid, merged in merged_by_sid.items():
        if sid is None:
            continue
        merged = sorted(merged, key=lambda c: c["t"])
        raw = raw_by_sid.get(sid, [])
        matches = sorted(matches_by_sid.get(sid, []), key=lambda m: m["crossing_t"])
        tracks = [m["track_id"] for m in matches]
        first_ci = merged[0]["t"]
        # time available in class = from walking in (walking from the door is door_to_room_s, not absence)
        avail = max(D - (matches[0]["crossing_t"] if matches else first_ci), 1e-6)

        intervals, exits = [], []
        for m in matches:
            outs = [t for t in exits_by_track.get(m["track_id"], []) if t > m["crossing_t"]]
            end = min(outs) if outs else D
            exits += outs[:1]
            intervals.append((max(0.0, m["crossing_t"]), min(D, end)))
        in_room = _union_length(intervals)
        last_end = max((b for _, b in intervals), default=None)
        left_early = (D - last_end) / D if last_end is not None and last_end < D - 1e-6 else 0.0

        my_pts = {t: pts_by_track.get(t, []) for t in tracks}
        all_pts = sorted((p for v in my_pts.values() for p in v), key=lambda p: p["t"])
        speed = max((_max_speed(v) for v in my_pts.values() if v), default=0.0)
        stab = float("nan")
        if intervals and all_pts:
            a, b = intervals[-1]
            late = [p for p in all_pts if (a + b) / 2 <= p["t"] <= b]
            if len(late) >= 3:
                xy = np.array([[p["x"], p["y"]] for p in late])
                mx, my = metres_per_unit()
                stab = float(np.hypot(xy[:, 0].std() * mx, xy[:, 1].std() * my))
        sims = [c.get("similarity") for c in raw if c.get("similarity") is not None]

        f = {
            "checkin_offset_ratio": first_ci / D if D > 0 else 0.0,
            "n_checkins": len(merged),
            "door_match_cost": max((m.get("cost", 0.0) for m in matches), default=CAP_COST),
            "door_to_room_s": matches[0]["dt"] if matches else CAP_DOOR_S,
            "time_in_room_ratio": min(1.0, in_room / avail) if matches else 0.0,
            "n_exits": len(exits),
            "left_early_ratio": left_early,
            "max_speed": speed,
            "seat_stability": stab,
            "n_name_conflicts": _conflicts(my_pts) if len(tracks) > 1 else 0,
            "n_spoof_flags": sum(int(c.get("spoof_flags", 0) or 0) for c in raw),
            "recog_similarity": float(np.mean(sims)) if sims else float("nan"),
        }
        rules, reasons = apply_rules(sid, f, sid in d3 or not matches, first_ci)
        rows.append({"student_id": sid, "features": f, "rules": rules, "reasons": reasons})
    return rows


def apply_rules(sid, f, never_entered, first_ci):
    rules, reasons = [], []
    if never_entered:
        rules.append("R1")
        reasons.append(f"R1: checked in at {first_ci:.1f} s but was never seen walking into the room")
    else:
        if f["time_in_room_ratio"] < RULES["R2_min_ratio"]:
            rules.append("R2")
            reasons.append(f"R2: in the room for only {f['time_in_room_ratio']:.0%} of the time after check-in")
        if f["left_early_ratio"] > RULES["R5_left_early"]:
            rules.append("R5")
            reasons.append(f"R5: left for good with {f['left_early_ratio']:.0%} of the session still to go")
    if f["n_name_conflicts"] > 0 or f["max_speed"] > RULES["R3_max_speed"]:
        rules.append("R3")
        why = (f"seen in two places at once ({f['n_name_conflicts']} s)" if f["n_name_conflicts"] > 0
               else f"position jumped at {f['max_speed']:.1f} m/s")
        reasons.append(f"R3: {why}")
    if f["n_checkins"] - f["n_exits"] > 1:
        rules.append("R4")
        reasons.append(f"R4: checked in {f['n_checkins']} times but left only {f['n_exits']} time(s)")
    return rules, reasons


def matrix(rows, medians=None):
    """Rows -> X (n x len(FEATURES)) with NaN replaced by the training medians."""
    X = np.array([[r["features"][k] for k in FEATURES] for r in rows], dtype=float).reshape(-1, len(FEATURES))
    if medians is not None:
        X = np.where(np.isnan(X), np.asarray(medians)[None, :], X)
    return X


def ml_scores(X, bundle_presence, which=None):
    """Anomaly score 0..1 of each row from the selected (or named) model of the trained bundle."""
    p = bundle_presence
    which = which or p["selected"]
    model = p["models"][which]
    if which == "iforest":
        raw = -model.score_samples(X)                 # higher = more anomalous
        lo, hi = p["iforest_range"]
        return np.clip((raw - lo) / max(hi - lo, 1e-9), 0, 1)
    return model.predict_proba(X)[:, 1]


def score_rows(rows, bundle_presence):
    """Add "ml_score", "score", "flagged" and an explanation for model-only flags."""
    if not rows:
        return rows
    p = bundle_presence
    X = matrix(rows, p["medians"])
    s = ml_scores(X, p)
    mean, std = np.asarray(p["normal_mean"]), np.asarray(p["normal_std"])
    for r, x, ml in zip(rows, X, s):
        r["ml_score"] = round(float(ml), 4)
        r["score"] = round(float(max(ml, p["rule_floor"] if r["rules"] else 0.0)), 4)
        r["flagged"] = bool(r["score"] >= p["threshold"])
        if r["flagged"] and not r["rules"]:
            z = np.abs((x - mean) / np.where(std > 1e-9, std, 1.0))
            top = [FEATURES[i] for i in np.argsort(-z)[:2]]
            r["reasons"] = [f"M: unusual pattern (model score {ml:.2f}); most unusual: {', '.join(top)}"]
        for k, v in r["features"].items():
            r["features"][k] = None if isinstance(v, float) and math.isnan(v) else round(float(v), 4)
    return rows
