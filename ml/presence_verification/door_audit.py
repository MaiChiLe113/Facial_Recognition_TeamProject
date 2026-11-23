"""Door audit: does every person who walks into the room have a check-in, and does every check-in
have a person walking in?  Owner: Đức Mạnh

1. detect_crossings(): door crossings (in / out) from the map trajectories (trajectories.py).
   Entry time = when the cam_2 track leaves the door area; cam_1 (corridor) corroborates it.
2. DtModel: learned distribution of dt = t(entry crossing) - t(check-in), a shifted log-normal plus a small
   uniform floor (camera clock drift, people waiting in the doorway).
3. audit(): optimal one-to-one assignment check-in <-> entry crossing (Hungarian, scipy), with a cost of
   "leaving it unmatched", so a pair is only made when it is more likely than both being unmatched.
   The pair cost is -log p(dt) - log(confidence) (mode "dt"), or -log P(pair) from a logistic-regression
   pair classifier trained on simulated sessions (mode "clf").
4. Alerts:  D1 entered without a check-in · D2 tailgating (entered right behind someone who checked in)
            · D3 checked in but nobody entered.

This module checks; it never renames tracks (ml/tracking/link_names.py does the naming) and never writes
to data/tracks/.
"""
import math

import numpy as np

from trajectories import zone_of

# --- crossing detection -------------------------------------------------------------------------------
GAP_S = 1.0             # door points closer than this in time belong to one door visit
MIN_DOOR_POINTS = 3     # a door visit needs at least this many points
CAM1_LAG_S = 2.0        # cam_1 loses people at the door ~2 s before cam_2 sees them leave the door area
                        # (take 1: 3.8, 3.4, 0.6, 0.9 s)
CORROBORATE_S = 3.0     # a cam_1 door visit this close to a cam_2 one is the same person

# --- matching -----------------------------------------------------------------------------------------
GATE_S = 60.0           # a check-in and an entry further apart than this are never paired
MERGE_S = 20.0          # check-ins of the same student closer than this are one check-in (tracker ID switch;
                        # take 3 has one 12 s apart)
TAILGATE_S = 4.0        # an unmatched entry this soon after a matched one is tailgating (D2), else D1
NEAR_S = 5.0            # "near" window for the pair-classifier features
BIG = 1e6


# ======================================================================================================
# 1. Door crossings
# ======================================================================================================
def _door_runs(points):
    """Maximal runs of door-zone points (gaps <= GAP_S). Returns [(i0, i1)] index ranges, inclusive."""
    runs, start = [], None
    for i, p in enumerate(points):
        at_door = p["zone"] == "door"
        if at_door and start is None:
            start = i
        elif at_door and points[i]["t"] - points[i - 1]["t"] > GAP_S:
            runs.append((start, i - 1))
            start = i
        elif not at_door and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(points) - 1))
    return [(a, b) for a, b in runs if b - a + 1 >= MIN_DOOR_POINTS]


def _visits(traj):
    """Door visits of one trajectory: [{t0, t1, n, prev, next}] with prev/next = zone before/after (None = the
    track starts/ends at the door)."""
    pts = traj["points"]
    out = []
    for a, b in _door_runs(pts):
        prev = next((pts[i]["zone"] for i in range(a - 1, -1, -1) if pts[i]["zone"] != "door"), None)
        nxt = next((pts[i]["zone"] for i in range(b + 1, len(pts)) if pts[i]["zone"] != "door"), None)
        out.append({"t0": pts[a]["t"], "t1": pts[b]["t"], "n": b - a + 1, "prev": prev, "next": nxt})
    return out


def _direction(prev, nxt):
    """in / out / None for a door visit, from the zones on either side of it. A track seen only at the door
    (prev and next None) counts as "in": on cam_2 people are lost as they walk past it into the room."""
    if prev in (None, "corridor") and nxt in (None, "room"):
        return "in"
    if prev == "room" and nxt in (None, "corridor"):
        return "out"
    return None


def detect_crossings(trajectories):
    """Door crossings from map trajectories ([{cam_id, track_id, points: [{t, x, y, zone}]}]).
    Returns [{id, t, track_id, cam_id, direction, confidence, door: [t0, t1], corroborated}] sorted by t."""
    cam2, cam1 = [], []
    for tr in trajectories:
        tid = f"{tr['cam_id']}:{tr['track_id']}"
        for v in _visits(tr):
            d = _direction(v["prev"], v["next"])
            if d is None:
                continue
            item = {"track_id": tid, "cam_id": tr["cam_id"], "direction": d, **v}
            (cam2 if tr["cam_id"] == "cam_2" else cam1).append(item)

    crossings, used_cam1 = [], set()
    for c in cam2:
        twins = [i for i, o in enumerate(cam1) if o["direction"] == c["direction"]
                 and o["t0"] <= c["t1"] + 1e-9 and o["t1"] >= c["t0"] - CORROBORATE_S]
        used_cam1.update(twins)
        conf = 0.5 + 0.25 * bool(twins) + 0.25 * min(1.0, c["n"] / 10)
        crossings.append({"t": c["t1"], "track_id": c["track_id"], "cam_id": "cam_2", "direction": c["direction"],
                          "confidence": round(conf, 3), "door": [c["t0"], c["t1"]], "corroborated": bool(twins)})
    for i, o in enumerate(cam1):            # cam_2 missed it: cam_1 alone, lower confidence
        if i in used_cam1:
            continue
        if o["direction"] == "in" and o["next"] is not None:   # cam_1 "in" only when it loses them at the door
            continue
        t = o["t1"] + (CAM1_LAG_S if o["direction"] == "in" else 0.0)
        crossings.append({"t": round(t, 3), "track_id": o["track_id"], "cam_id": "cam_1", "direction": o["direction"],
                          "confidence": 0.4, "door": [o["t0"], o["t1"]], "corroborated": False})
    crossings.sort(key=lambda c: c["t"])
    for k, c in enumerate(crossings):
        c["id"] = f"x{k}"
    return crossings


def trajectories_from_points(points):
    """Flat points [{t, track_id, x, y, cam_id?}] (the infer.py contract) -> trajectories with zones."""
    by_track = {}
    for p in points:
        by_track.setdefault(str(p["track_id"]), []).append(p)
    out = []
    for tid, pts in by_track.items():
        pts = sorted(pts, key=lambda p: p["t"])
        cam = pts[0].get("cam_id") or (tid.split(":", 1)[0] if ":" in tid else "cam_2")
        raw_id = tid.split(":", 1)[1] if tid.startswith(f"{cam}:") else tid
        out.append({"cam_id": cam, "track_id": raw_id,
                    "points": [{"t": float(p["t"]), "x": float(p["x"]), "y": float(p["y"]),
                                "zone": zone_of(float(p["x"]), float(p["y"]))} for p in pts]})
    return out


# ======================================================================================================
# 2. dt model
# ======================================================================================================
class DtModel:
    """p(dt) for dt = entry - check-in: (1 - w) * LogNormal(dt + shift; mu, sigma) + w * Uniform(-shift, GATE_S)."""

    def __init__(self, mu=math.log(6.0), sigma=0.6, shift=2.0, w_uniform=0.05, n=0):
        self.mu, self.sigma, self.shift, self.w, self.n = float(mu), float(sigma), float(shift), float(w_uniform), n

    @classmethod
    def fit(cls, dts, shift=2.0, w_uniform=0.05, min_sigma=0.3):
        d = np.asarray([x for x in dts if -shift < x < GATE_S], dtype=float)
        if len(d) < 2:
            return cls(shift=shift, w_uniform=w_uniform, n=len(d))
        z = np.log(d + shift)
        return cls(float(z.mean()), max(min_sigma, float(z.std(ddof=1))), shift, w_uniform, len(d))

    def logpdf(self, dt):
        dt = np.asarray(dt, dtype=float)
        x = dt + self.shift
        ok = (x > 0) & (dt <= GATE_S)
        with np.errstate(divide="ignore", invalid="ignore"):
            ln = np.exp(-(np.log(np.where(ok, x, 1.0)) - self.mu) ** 2 / (2 * self.sigma ** 2)) / (
                np.where(ok, x, 1.0) * self.sigma * math.sqrt(2 * math.pi))
            dens = (1 - self.w) * ln + self.w / (GATE_S + self.shift)
            return np.where(ok, np.log(dens), -np.inf)

    def sample(self, n, rng):
        return np.exp(rng.normal(self.mu, self.sigma, n)) - self.shift

    def median(self):
        return math.exp(self.mu) - self.shift

    def to_dict(self):
        return {"mu": self.mu, "sigma": self.sigma, "shift": self.shift, "w_uniform": self.w, "n": self.n,
                "median_s": round(self.median(), 2)}

    @classmethod
    def from_dict(cls, d):
        return cls(d["mu"], d["sigma"], d["shift"], d["w_uniform"], d.get("n", 0))


# ======================================================================================================
# 3. Matching
# ======================================================================================================
PAIR_FEATURES = ["dt", "dt_logpdf", "confidence", "n_entries_near", "n_checkins_near", "gap_prev_entry",
                 "gap_next_entry", "corroborated", "entries_between", "checkins_between", "queue_ahead",
                 "checkin_at_door", "door_gap_s"]
DOOR_SLACK_S = 1.0      # the check-in may fall this far outside the track's time at the door


def merge_check_ins(check_ins):
    """Same student checked in again within MERGE_S -> one check-in (the first). Keeps the count."""
    merged = []
    last = {}
    for c in sorted(check_ins, key=lambda c: c["t"]):
        sid = c.get("student_id")
        prev = last.get(sid)
        if sid is not None and prev is not None and c["t"] - prev["t"] <= MERGE_S:
            prev["merged"] += 1
            continue
        item = {**c, "merged": 1}
        merged.append(item)
        last[sid] = item
    return merged


def pair_features(check_ins, entries, dt_model):
    """Feature matrix [n_check_ins, n_entries, len(PAIR_FEATURES)] and a gate mask."""
    n, m = len(check_ins), len(entries)
    ct = np.array([c["t"] for c in check_ins], dtype=float)
    et = np.array([e["t"] for e in entries], dtype=float)
    F = np.zeros((n, m, len(PAIR_FEATURES)))
    if n == 0 or m == 0:
        return F, np.zeros((n, m), bool)
    dt = et[None, :] - ct[:, None]
    gate = (dt > -dt_model.shift) & (dt <= GATE_S)
    lp = dt_model.logpdf(dt)
    conf = np.array([e.get("confidence", 1.0) for e in entries])
    corr = np.array([float(bool(e.get("corroborated", False))) for e in entries])
    near_e = np.array([(np.abs(et - t) <= NEAR_S).sum() - 1 for t in et])
    near_c = np.array([(np.abs(ct - t) <= NEAR_S).sum() - 1 for t in ct])
    order = np.sort(et)
    gap_prev = np.array([min(30.0, t - order[order < t].max()) if (order < t).any() else 30.0 for t in et])
    gap_next = np.array([min(30.0, order[order > t].min() - t) if (order > t).any() else 30.0 for t in et])
    F[..., 0] = np.clip(dt, -10, GATE_S + 10)
    F[..., 1] = np.clip(np.where(np.isfinite(lp), lp, -30.0), -30, 5)
    F[..., 2] = conf[None, :]
    F[..., 3] = near_e[None, :]
    F[..., 4] = near_c[:, None]
    F[..., 5] = gap_prev[None, :]
    F[..., 6] = gap_next[None, :]
    F[..., 7] = corr[None, :]
    # order at the door (one person at a time): for a right pair, the entries between the check-in and the
    # entry are about the people still queueing ahead, and later check-ins mostly enter later
    lo = np.minimum(ct[:, None], et[None, :])
    hi = np.maximum(ct[:, None], et[None, :])
    F[..., 8] = ((et[None, None, :] > lo[..., None]) & (et[None, None, :] < hi[..., None])).sum(-1)
    F[..., 9] = ((ct[None, None, :] > lo[..., None]) & (ct[None, None, :] < hi[..., None])).sum(-1)
    ahead = np.array([((ct < t) & (ct > t - GATE_S)).sum() - ((et < t) & (et > t - GATE_S)).sum() for t in ct])
    F[..., 10] = np.clip(ahead, -5, 10)[:, None] - F[..., 8]
    # the attendance camera is in the doorway: whoever checked in was standing at the door at that moment,
    # so the right entry crossing's door visit should contain the check-in time (take 1, 4, 8: 6 of 6)
    d0 = np.array([e.get("door", [e["t"], e["t"]])[0] for e in entries], dtype=float)
    d1 = np.array([e.get("door", [e["t"], e["t"]])[1] for e in entries], dtype=float)
    gap = np.maximum(0.0, np.maximum(d0[None, :] - ct[:, None], ct[:, None] - d1[None, :]))
    F[..., 11] = (gap <= DOOR_SLACK_S).astype(float)
    F[..., 12] = np.clip(gap, 0, 30.0)
    return F, gate


def _pair_costs(check_ins, entries, dt_model, pair_model):
    """Pair cost (for the assignment) and p (how plausible the pair is, 0..1, for the alert scores)."""
    F, gate = pair_features(check_ins, entries, dt_model)
    n, m = gate.shape
    if n == 0 or m == 0:
        return np.zeros((n, m)) + BIG, np.zeros((n, m)), gate
    conf = np.clip(F[..., 2], 1e-3, 1.0)
    if pair_model is None:
        cost = -F[..., 1] - np.log(conf)
        peak = float(dt_model.logpdf(np.array([dt_model.median()]))[0])
        p = np.exp(np.clip(F[..., 1] - peak, -50, 0)) * conf          # density relative to its peak
    else:
        p = pair_model.predict_proba(F.reshape(-1, F.shape[-1]))[:, 1].reshape(n, m)
        cost = -np.log(np.clip(p, 1e-9, 1.0))
    return np.where(gate, cost, BIG), np.where(gate, p, 0.0), gate


def assign(cost, unmatched_cost):
    """Optimal assignment with "unmatched" options. Returns [(i, j)] pairs whose cost is below BIG."""
    from scipy.optimize import linear_sum_assignment

    n, m = cost.shape
    if n == 0 or m == 0:
        return []
    size = n + m
    A = np.full((size, size), BIG)
    A[:n, :m] = cost
    A[:n, m:] = np.where(np.eye(n, dtype=bool), unmatched_cost, BIG)      # check-in i left unmatched
    A[n:, :m] = np.where(np.eye(m, dtype=bool), unmatched_cost, BIG)      # entry j left unmatched
    A[n:, m:] = 0.0
    rows, cols = linear_sum_assignment(A)
    return [(int(i), int(j)) for i, j in zip(rows, cols) if i < n and j < m and cost[i, j] < BIG]


def audit(check_ins, crossings, dt_model, pair_model=None, unmatched_cost=4.0, min_alert_score=0.0):
    """Match check-ins to entry crossings and raise alerts.

    check_ins: [{t, student_id, ...}] (raw; duplicates within MERGE_S are merged)
    crossings: detect_crossings() output (only direction "in" is matched)
    Alert score: D1/D2 = crossing confidence x (1 - how well the entry fits a check-in that is still
    unmatched); D3 = 1 - how well the check-in fits an entry that is still unmatched. Alerts scoring below
    min_alert_score (tuned on validation sessions) go to "suppressed" instead of "alerts".
    Returns {"check_ins": merged, "matches": [...], "alerts": [...], "suppressed": [...]}.
    """
    merged = merge_check_ins(check_ins)
    entries = [c for c in crossings if c["direction"] == "in"]
    cost, p_pair, gate = _pair_costs(merged, entries, dt_model, pair_model)
    pairs = assign(cost, unmatched_cost)

    matches, matched_c, matched_e = [], set(), set()
    for i, j in pairs:
        c, e = merged[i], entries[j]
        matched_c.add(i)
        matched_e.add(j)
        matches.append({"student_id": c.get("student_id"), "check_in_t": c["t"], "crossing_id": e["id"],
                        "track_id": e["track_id"], "crossing_t": e["t"], "dt": round(e["t"] - c["t"], 2),
                        "cost": round(float(cost[i, j]), 3), "p": round(float(p_pair[i, j]), 3)})

    alerts = []
    matched_times = sorted(entries[j]["t"] for j in matched_e)
    free_c = [i for i in range(len(merged)) if i not in matched_c]
    free_e = [j for j in range(len(entries)) if j not in matched_e]
    for j, e in enumerate(entries):
        if j in matched_e:
            continue
        before = [t for t in matched_times if 0 <= e["t"] - t <= TAILGATE_S]
        best = float(p_pair[free_c, j].max()) if free_c else 0.0
        score = round(e.get("confidence", 1.0) * (1 - best), 3)
        if before:
            lead = next(m for m in matches if m["crossing_t"] == before[-1])
            alerts.append({"code": "D2", "t": e["t"], "crossing_id": e["id"],
                           "track_ids": [e["track_id"], lead["track_id"]],
                           "student_id": lead["student_id"], "score": score,
                           "reason": f"Entered {e['t'] - before[-1]:.1f} s behind {lead['student_id']} "
                                     f"without a check-in of their own (tailgating)"})
        else:
            alerts.append({"code": "D1", "t": e["t"], "crossing_id": e["id"], "track_ids": [e["track_id"]],
                           "student_id": None, "score": score, "reason": "Walked into the room with no matching check-in"})
    for i, c in enumerate(merged):
        if i in matched_c:
            continue
        best = float(p_pair[i, free_e].max()) if free_e else 0.0
        alerts.append({"code": "D3", "t": c["t"], "track_ids": [], "student_id": c.get("student_id"),
                       "score": round(1 - best, 3),
                       "reason": f"{c.get('student_id')} checked in but nobody was seen walking into the room"})
    alerts.sort(key=lambda a: a["t"])
    kept = [a for a in alerts if a["score"] >= min_alert_score]
    suppressed = [a for a in alerts if a["score"] < min_alert_score]
    return {"check_ins": merged, "matches": matches, "alerts": kept, "suppressed": suppressed}


def window_baseline(check_ins, crossings, window=(0.0, 15.0)):
    """Rule baseline in the spirit of link_names.py: each check-in takes the first free entry crossing
    0-15 s after it. Same output shape as audit() (no costs)."""
    merged = merge_check_ins(check_ins)
    entries = [c for c in crossings if c["direction"] == "in"]
    used, matches = set(), []
    for c in merged:
        for j, e in enumerate(entries):
            if j not in used and window[0] <= e["t"] - c["t"] <= window[1]:
                used.add(j)
                matches.append({"student_id": c.get("student_id"), "check_in_t": c["t"], "crossing_id": e["id"],
                                "track_id": e["track_id"], "crossing_t": e["t"], "dt": round(e["t"] - c["t"], 2)})
                break
    matched_ci = {(m["student_id"], m["check_in_t"]) for m in matches}
    alerts = [{"code": "D1", "t": e["t"], "crossing_id": e["id"], "track_ids": [e["track_id"]], "student_id": None,
               "score": 1.0, "reason": ""}
              for j, e in enumerate(entries) if j not in used]
    alerts += [{"code": "D3", "t": c["t"], "track_ids": [], "student_id": c.get("student_id"), "score": 1.0, "reason": ""}
               for c in merged if (c.get("student_id"), c["t"]) not in matched_ci]
    return {"check_ins": merged, "matches": matches, "alerts": sorted(alerts, key=lambda a: a["t"])}
