"""Scoring helpers shared by train.py and evaluate.py.  Owner: Đức Mạnh"""
import numpy as np

from door_audit import audit, merge_check_ins, pair_features, window_baseline
from presence import student_rows

ENTRY_FRAUD = ("tailgate", "no_checkin")


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tp": tp, "fp": fp, "fn": fn}


def run_door(session, mode, bundle_door, dt_model):
    """Door audit of one session with mode "window" (rule baseline), "dt" or "clf"."""
    if mode == "window":
        return window_baseline(session["check_ins"], session["crossings"])
    clf = bundle_door.get("pair_clf") if mode == "clf" else None
    u = bundle_door["u_clf"] if mode == "clf" else bundle_door["u_dt"]
    min_score = bundle_door.get("min_score_clf" if mode == "clf" else "min_score_dt", 0.0)
    return audit(session["check_ins"], session["crossings"], dt_model, clf, u, min_score)


def door_scores(sessions, results):
    """Entry alerts (D1+D2) vs crossings labelled tailgate / no_checkin; D3 vs students who never entered;
    match accuracy vs the true check-in -> crossing pairs."""
    e_tp = e_fp = e_fn = d3_tp = d3_fp = d3_fn = 0
    codes = {"D1": [0, 0, 0], "D2": [0, 0, 0]}
    correct = n_pairs = 0
    for s, r in zip(sessions, results):
        truth = s["truth"]["entries"]
        pos = {cid for cid, lab in truth.items() if lab in ENTRY_FRAUD}
        pred = {a["crossing_id"] for a in r["alerts"] if a["code"] in ("D1", "D2")}
        e_tp += len(pos & pred)
        e_fp += len(pred - pos)
        e_fn += len(pos - pred)
        for code, lab in (("D1", "no_checkin"), ("D2", "tailgate")):
            p_c = {a["crossing_id"] for a in r["alerts"] if a["code"] == code}
            t_c = {cid for cid, l in truth.items() if l == lab}
            codes[code][0] += len(p_c & t_c)
            codes[code][1] += len(p_c - t_c)
            codes[code][2] += len(t_c - p_c)
        no_entry = set(s["truth"]["no_entry"])
        d3 = {a["student_id"] for a in r["alerts"] if a["code"] == "D3"}
        d3_tp += len(d3 & no_entry)
        d3_fp += len(d3 - no_entry)
        d3_fn += len(no_entry - d3)
        true_pairs = {(round(t, 3), c) for t, c in s["truth"]["pairs"]}
        detected = {c["id"] for c in s["crossings"]}
        true_pairs = {p for p in true_pairs if p[1] in detected}
        n_pairs += len(true_pairs)
        correct += sum((round(m["check_in_t"], 3), m["crossing_id"]) in true_pairs for m in r["matches"])
    out = {"entry_alerts": prf(e_tp, e_fp, e_fn), "D3": prf(d3_tp, d3_fp, d3_fn),
           "D1": prf(*codes["D1"]), "D2": prf(*codes["D2"]),
           "match_accuracy": round(correct / n_pairs, 4) if n_pairs else None}
    out["mean_f1"] = round((out["entry_alerts"]["f1"] + out["D3"]["f1"]) / 2, 4)
    return out


def pair_training_data(sessions, dt_model):
    """Gated candidate pairs (check-in, entry crossing) with label 1 for the true pairs."""
    Xs, ys = [], []
    for s in sessions:
        merged = merge_check_ins(s["check_ins"])
        entries = [c for c in s["crossings"] if c["direction"] == "in"]
        F, gate = pair_features(merged, entries, dt_model)
        true_pairs = {(round(t, 3), c) for t, c in s["truth"]["pairs"]}
        for i, c in enumerate(merged):
            for j, e in enumerate(entries):
                if gate[i, j]:
                    Xs.append(F[i, j])
                    ys.append(int((round(c["t"], 3), e["id"]) in true_pairs))
    return np.array(Xs), np.array(ys)


def presence_data(sessions, door_results):
    """Rows (with labels and anomaly types) of every checked-in student of every session."""
    rows = []
    for s, r in zip(sessions, door_results):
        truth = s.get("truth", {}).get("students", {})
        for row in student_rows(s, r):
            t = truth.get(row["student_id"], {"anomaly": 0, "type": "normal"})
            row["label"], row["type"] = t["anomaly"], t["type"]
            rows.append(row)
    return rows


def auc(y, s):
    from sklearn.metrics import roc_auc_score
    y = np.asarray(y)
    return round(float(roc_auc_score(y, s)), 4) if 0 < y.sum() < len(y) else None


def best_threshold(y, s):
    best = (0.5, -1.0)
    for t in np.linspace(0.05, 0.95, 91):
        pred = np.asarray(s) >= t
        tp = int((pred & (np.asarray(y) == 1)).sum())
        fp = int((pred & (np.asarray(y) == 0)).sum())
        fn = int((~pred & (np.asarray(y) == 1)).sum())
        f = prf(tp, fp, fn)["f1"]
        if f > best[1]:
            best = (round(float(t), 3), f)
    return best
