"""Synthetic class sessions on the Room 204 map, with labels, for training and testing.  Owner: Đức Mạnh

The real takes are too few and too short to train on (8 takes, 6-49 s, at most 4 people, no fraud), so the
models train on simulated sessions whose parameters come from the real takes:
  - dt check-in -> entry: sampled from the DtModel fitted on the real takes (train.py)
  - walking speed 0.9-1.8 m/s, seat jitter, heavy-tailed coordinate noise (homography error and box jumps,
    matched to the recorded takes), missed / spurious crossings

A session has the same shape as a real one (sessions.real_session):
    {"duration", "check_ins": [{t, student_id, similarity, spoof_flags}],
     "crossings": [{id, t, track_id, cam_id, direction, confidence, corroborated}],
     "points": [{t, track_id, cam_id, x, y}],
     "truth": {"students": {sid: {"anomaly": 0/1, "type": str}},
               "entries": {crossing_id: "checked_in" | "tailgate" | "no_checkin" | "noise"},
               "no_entry": [sid, ...], "pairs": [[check-in t, crossing_id], ...]}}

Crossings are simulated directly (the detector itself is tested on the real takes); trajectories are
simulated for presence features (time in room, speed, seat stability, two places at once).
"""
import math

import numpy as np

from door_audit import MERGE_S, DtModel
from pv_common import metres_per_unit

WALK_MPS = (0.9, 1.8)            # walking speed range (m/s); recorded takes measure up to ~2.4 m/s with jitter
NOISE_DF = 3                     # Student-t noise: mostly small, sometimes a box jumps (real p99 1-s step 2.3 m)
DOOR_IN = (0.33, 0.875)          # just inside the door

# Per-student anomaly types. "rule" ones are what R1-R5 are written for; "model" ones have no rule.
STUDENT_ANOMALIES = {
    "no_entry": "rule",      # R1 / D3: checks in, never enters
    "short_stay": "rule",    # R2 (+R5): leaves after a small part of the class
    "early_leave": "rule",   # R5: leaves well before the end
    "impostor": "rule",      # R3 + R4: a second person checks in with the same identity while they are inside
    "late": "model",         # checks in very late (no rule)
    "loiter": "model",       # long wait between check-in and walking in (no rule)
}
QUEUE_S = 5.0                    # check-ins this close are one queue at the door
P_FIFO = 0.85                    # chance that someone does not overtake the person ahead at the door
SHORT_TYPES = ["no_entry", "short_stay", "early_leave", "impostor"]       # fit in a 30-120 s session


def _m2u():
    mx, my = metres_per_unit()
    return 1 / mx, 1 / my            # map units per metre in x, y


def _walk(rng, start, end, t0, step):
    """Points walking from start to end at WALK_MPS, starting at t0. Returns ([(t, x, y)], t_arrive)."""
    ux, uy = _m2u()
    dist_m = math.hypot((end[0] - start[0]) / ux, (end[1] - start[1]) / uy)
    dur = max(step, dist_m / rng.uniform(*WALK_MPS))
    ts = np.arange(t0, t0 + dur, step)
    f = (ts - t0) / dur
    return [(t, start[0] + (end[0] - start[0]) * a, start[1] + (end[1] - start[1]) * a) for t, a in zip(ts, f)], t0 + dur


def _sit(rng, seat, t0, t1, step):
    ux, uy = _m2u()
    ts = np.arange(t0, t1, step)
    return [(t, seat[0] + rng.normal(0, 0.08) * ux, seat[1] + rng.normal(0, 0.08) * uy) for t in ts]


def _seat(rng):
    return (rng.uniform(0.42, 0.95), rng.uniform(0.15, 0.9))


class _Builder:
    def __init__(self, rng, duration, step, noise_m, p_miss):
        self.rng, self.D, self.step, self.noise_m, self.p_miss = rng, duration, step, noise_m, p_miss
        self.check_ins, self.crossings, self.points = [], [], []
        self.entry_truth, self.n_tracks = {}, 0
        self.pairs = []                 # true (check-in time, crossing id) pairs
        self._last_ci = None

    def new_track(self):
        self.n_tracks += 1
        return f"cam_2:{self.n_tracks}"

    def crossing(self, t, track, direction, truth=None, conf=None, after_check_in=False, door_from=None):
        if not 0 <= t <= self.D:
            return None
        if truth != "noise" and self.rng.random() < self.p_miss:
            return None                                          # the detector missed it
        cid = f"x{len(self.crossings)}"
        c = 0.4 + 0.6 * self.rng.beta(6, 2) if conf is None else conf
        t0 = t - self.rng.uniform(0.5, 2.5) if door_from is None else min(door_from, t - 0.3)
        t0 += self.rng.normal(0, 0.4)                            # the detector's error on the door visit
        self.crossings.append({"id": cid, "t": round(float(t), 3), "track_id": track, "cam_id": "cam_2",
                               "direction": direction, "confidence": round(float(c), 3),
                               "corroborated": bool(self.rng.random() < 0.6),
                               "door": [round(float(min(t0, t)), 3), round(float(t), 3)]})
        if direction == "in" and truth:
            self.entry_truth[cid] = truth
        if after_check_in and self._last_ci is not None:
            self.pairs.append((self._last_ci, cid))
        return cid

    def add_points(self, track, pts):
        ux, uy = _m2u()
        for t, x, y in pts:
            if 0 <= t <= self.D:
                nx, ny = self.rng.standard_t(NOISE_DF, 2) * self.noise_m
                self.points.append({"t": round(float(t), 2), "track_id": track, "cam_id": "cam_2",
                                    "x": round(float(x + nx * ux), 4), "y": round(float(y + ny * uy), 4)})

    def stay(self, track, t_enter, t_leave, seat):
        """In the room from t_enter (at the door) to t_leave (back at the door, or the end of the session)."""
        walk_in, t_seat = _walk(self.rng, DOOR_IN, seat, t_enter, self.step)
        self.add_points(track, walk_in)
        if t_leave >= self.D:
            self.add_points(track, _sit(self.rng, seat, t_seat, self.D, self.step))
            return None
        walk_out_dur = _walk(self.rng, seat, DOOR_IN, 0, self.step)[1]
        t_up = max(t_seat, t_leave - walk_out_dur)
        self.add_points(track, _sit(self.rng, seat, t_seat, t_up, self.step))
        walk_out, t_door = _walk(self.rng, seat, DOOR_IN, t_up, self.step)
        self.add_points(track, walk_out)
        return t_door

    def check_in(self, t, sid, similarity=None, spoof=0):
        self._last_ci = None
        if 0 <= t <= self.D:
            self._last_ci = round(float(t), 3)
            sim = self.rng.uniform(0.55, 0.92) if similarity is None else similarity
            self.check_ins.append({"t": round(float(t), 3), "student_id": sid, "similarity": round(float(sim), 3),
                                   "spoof_flags": int(spoof)})


def simulate_session(rng, dt_model, kind="long", p_anomaly=0.12, p_tailgate=0.25, p_no_checkin=0.25,
                     noise_m=0.12, p_miss=0.04, spurious_rate=None, clock_jitter_s=0.0):
    """One labelled session. kind: "short" (30-120 s, like the recorded takes) or "long" (30-90 min class)."""
    if kind == "short":
        D, n, step = rng.uniform(30, 120), int(rng.integers(2, 9)), 0.5
        arrive = (0.0, 0.45)
    else:
        D, n, step = rng.uniform(1800, 5400), int(rng.integers(8, 31)), 5.0
        arrive = (0.0, 0.12)
    b = _Builder(rng, D, step, noise_m, p_miss)
    truth_students, no_entry = {}, []

    # arrivals in small groups (people walk in together, like take 3)
    t_group, left = rng.uniform(*arrive) * D, n
    sids = [f"S{k:03d}" for k in range(n)]
    arrivals = []
    while left > 0:
        g = min(left, int(rng.choice([1, 1, 1, 2, 2, 3])))
        for k in range(g):
            arrivals.append(t_group + k * rng.uniform(0.3, 2.0))
        left -= g
        t_group += rng.exponential(D * (arrive[1] - arrive[0]) / max(1, n / 1.5))
    arrivals = sorted(min(a, D * 0.9 - 15) for a in arrivals)     # leave time to walk in before the end

    types = SHORT_TYPES if kind == "short" else list(STUDENT_ANOMALIES)
    entry_times = []
    last_in, last_ci = -1e9, -1e9    # one door: people queueing together walk in in check-in order
    for sid, t_ci in zip(sids, arrivals):
        kind_a = str(rng.choice(types)) if rng.random() < p_anomaly else None
        truth_students[sid] = {"anomaly": int(kind_a is not None), "type": kind_a or "normal"}
        if kind_a == "late":
            t_ci = rng.uniform(0.5, 0.85) * D
        spoof = int(rng.random() < 0.03)
        b.check_in(t_ci + rng.normal(0, clock_jitter_s), sid, spoof=spoof)
        if kind_a == "no_entry":
            no_entry.append(sid)
            continue
        dt = float(np.clip(dt_model.sample(1, rng)[0], 0.2, 45.0))
        if kind_a == "loiter":
            dt = rng.uniform(25.0, 55.0)
        t_in = t_ci + dt
        if (kind_a != "loiter" and t_ci - last_ci <= QUEUE_S and t_in < last_in + 0.5
                and rng.random() < P_FIFO):
            t_in = last_in + rng.uniform(0.5, 1.5)
        last_in, last_ci = t_in, t_ci
        track, seat = b.new_track(), _seat(rng)
        at_door = t_ci - rng.uniform(0.3, 1.5) if kind_a != "loiter" else t_in - rng.uniform(1.0, 4.0)
        b.crossing(t_in, track, "in", "checked_in", after_check_in=True, door_from=at_door)
        entry_times.append(t_in)
        avail = D - t_in
        if kind_a == "short_stay":
            t_leave = t_in + rng.uniform(0.05, 0.35) * avail
        elif kind_a == "early_leave":
            t_leave = t_in + rng.uniform(0.4, 0.72) * avail
        elif kind == "long" and rng.random() < 0.25:
            t_leave = D - rng.uniform(0.0, 0.04) * D            # packs up just before the end
        else:
            t_leave = D + 1
        # a normal break: out and back in, checked in again on the way back (long sessions only)
        if kind_a is None and kind == "long" and rng.random() < 0.15:
            t_out = t_in + rng.uniform(0.25, 0.6) * avail
            t_door = b.stay(track, t_in, t_out, seat)
            if t_door is not None:
                b.crossing(t_door, track, "out")
                t_back = t_door + rng.uniform(0.02, 0.08) * D
                b.check_in(t_back, sid)
                track2 = b.new_track()
                t_in2 = t_back + float(np.clip(dt_model.sample(1, rng)[0], 0.2, 45.0))
                b.crossing(t_in2, track2, "in", "checked_in", after_check_in=True,
                           door_from=t_back - rng.uniform(0.3, 1.5))
                t_door2 = b.stay(track2, t_in2, t_leave, seat)
                if t_door2 is not None:
                    b.crossing(t_door2, track2, "out")
            continue
        t_door = b.stay(track, t_in, t_leave, seat)
        if t_door is not None:
            b.crossing(t_door, track, "out")
        if kind_a == "impostor":                    # someone else checks in as sid while sid is inside
            t_ci2 = max(t_in + rng.uniform(0.1, 0.5) * (min(t_leave, D) - t_in), t_ci + MERGE_S + 5)
            if t_ci2 > min(t_leave, D) - 5:         # no time left in this session: it did not happen
                truth_students[sid] = {"anomaly": 0, "type": "normal"}
                continue
            b.check_in(t_ci2, sid, similarity=rng.uniform(0.5, 0.7))
            track2 = b.new_track()
            t_in2 = t_ci2 + float(np.clip(dt_model.sample(1, rng)[0], 0.2, 45.0))
            b.crossing(t_in2, track2, "in", "checked_in", after_check_in=True,
                       door_from=t_ci2 - rng.uniform(0.3, 1.5))
            b.stay(track2, t_in2, D + 1, _seat(rng))

    # door-level fraud: tailgating right behind someone, and walking in with no check-in at all
    if entry_times and rng.random() < p_tailgate:
        lead = float(rng.choice(entry_times))
        tr = b.new_track()
        if b.crossing(lead + rng.uniform(0.5, 3.0), tr, "in", "tailgate"):
            b.stay(tr, lead + 2, D + 1, _seat(rng))
    if rng.random() < p_no_checkin:
        t = rng.uniform(0.05, 0.9) * D
        tr = b.new_track()
        if b.crossing(t, tr, "in", "no_checkin"):
            b.stay(tr, t, D + 1, _seat(rng))
    # spurious detections (tracker noise at the door)
    lam = (0.15 if kind == "short" else 0.4) if spurious_rate is None else spurious_rate
    for _ in range(rng.poisson(lam)):
        b.crossing(rng.uniform(0, D), b.new_track(), "in", "noise", conf=float(rng.uniform(0.3, 0.6)))

    b.crossings.sort(key=lambda c: c["t"])
    b.check_ins.sort(key=lambda c: c["t"])
    return {"duration": round(float(D), 2), "kind": kind, "check_ins": b.check_ins, "crossings": b.crossings,
            "points": b.points,
            "truth": {"students": truth_students, "entries": b.entry_truth, "no_entry": no_entry,
                      "pairs": [[t, c] for t, c in b.pairs]}}


def simulate(n, seed, dt_model=None, short_share=0.5, **kw):
    """n sessions, reproducible from seed."""
    rng = np.random.default_rng(seed)
    dt_model = dt_model or DtModel()
    return [simulate_session(rng, dt_model, "short" if rng.random() < short_share else "long", **kw)
            for _ in range(n)]


if __name__ == "__main__":
    import json
    s = simulate(1, 0)[0]
    print(json.dumps({k: (v if k in ("duration", "kind", "truth") else len(v)) for k, v in s.items()}, indent=1))
