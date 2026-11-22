"""Numbers and figures for the report.  Owner: Đức Mạnh

    .venv/Scripts/python ml/presence_verification/evaluate.py          # needs presence_verification.joblib
    .venv/Scripts/python ml/presence_verification/evaluate.py --quick  # small test set

Writes outputs/eval/report.json, outputs/eval/report.md and (with matplotlib) outputs/eval/*.png.

1. Door audit on the simulated test set: rule baseline (fixed window, like link_names.py) vs dt model +
   Hungarian vs pair classifier. Robustness to camera clock jitter.
2. Presence on the simulated test set: rules only vs IsolationForest vs LogisticRegression vs RandomForest;
   recall per anomaly type; feature-group ablation; robustness to map-coordinate noise.
3. The recorded takes: crossings vs the hand-labelled entries (take 1, 3), alerts on every take, scores of
   every checked-in student. These are all normal takes (no fraud was recorded yet).
"""
import argparse
import time

import numpy as np

from door_audit import DtModel
from presence import GROUPS, FEATURES, matrix, ml_scores, score_rows, student_rows
from pv_common import MODEL_FILE, OUTPUTS, load_ground_truth, takes, write_json
from pv_metrics import auc, door_scores, presence_data, prf, run_door
from sessions import real_session
from simulate import simulate
from train import SEEDS, final_scores

OUT = OUTPUTS / "eval"


def _pr_at(y, s, thr):
    y, pred = np.asarray(y), np.asarray(s) >= thr
    return prf(int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum()), int((~pred & (y == 1)).sum()))


def door_section(test, bundle, dt_model):
    door = bundle["door"]
    out = {m: door_scores(test, [run_door(s, m, door, dt_model) for s in test]) for m in ("window", "dt", "clf")}
    jitter = {}
    for sigma in (0.0, 2.0, 5.0):
        rng = np.random.default_rng(7)
        shaken = []
        for s in test:
            s2 = {**s, "crossings": [{**c, "t": c["t"] + rng.normal(0, sigma)} for c in s["crossings"]]}
            shaken.append(s2)
        jitter[sigma] = {m: door_scores(shaken, [run_door(s, m, door, dt_model) for s in shaken])["mean_f1"]
                         for m in ("window", "dt", "clf")}
    out["clock_jitter_mean_f1"] = jitter
    return out


def presence_section(test, bundle, dt_model, train_rows):
    door, pres = bundle["door"], bundle["presence"]
    rows = presence_data(test, [run_door(s, door["mode"], door, dt_model) for s in test])
    y = np.array([r["label"] for r in rows])
    X = matrix(rows, pres["medians"])
    rule = np.array([1.0 if r["rules"] else 0.0 for r in rows])
    out = {"rows": len(rows), "anomalies": int(y.sum()), "models": {}}
    out["models"]["rules_only"] = {"auc": auc(y, rule), **_pr_at(y, rule, 0.5)}
    for m in pres["models"]:
        ml = ml_scores(X, pres, m)
        fin = final_scores(rows, pres, m)
        out["models"][m] = {"auc_model_only": auc(y, ml), "auc": auc(y, fin), **_pr_at(y, fin, pres["threshold"])}
    sel = final_scores(rows, pres)
    flagged = sel >= pres["threshold"]
    types = sorted({r["type"] for r in rows if r["label"]})
    out["recall_by_type"] = {}
    for t in types:
        idx = np.array([r["type"] == t for r in rows])
        out["recall_by_type"][t] = {"n": int(idx.sum()), "rules": round(float(rule[idx].mean()), 3),
                                    "selected_model": round(float(flagged[idx].mean()), 3)}
    normal = y == 0
    out["false_alarm_rate"] = {"rules": round(float(rule[normal].mean()), 4),
                               "selected_model": round(float(flagged[normal].mean()), 4)}
    # ablation: logistic regression without each feature group (retrained on the same train rows)
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    Xtr, ytr = matrix(train_rows, pres["medians"]), np.array([r["label"] for r in train_rows])
    abl = {}
    for g, names in {"none": [], **GROUPS}.items():
        keep = [i for i, f in enumerate(FEATURES) if f not in names]
        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
        clf.fit(Xtr[:, keep], ytr)
        abl[f"without_{g}" if g != "none" else "all_features"] = auc(y, clf.predict_proba(X[:, keep])[:, 1])
    out["ablation_logreg_auc"] = abl
    return out, rows, sel


def noise_section(bundle, dt_model, n, train_rows):
    """Presence AUC (selected model, trained once) when the map coordinates are noisier than in training."""
    door, pres = bundle["door"], bundle["presence"]
    res = {}
    for noise in (0.12, 0.3, 0.6):
        test = simulate(n, SEEDS["test"], dt_model, noise_m=noise)
        rows = presence_data(test, [run_door(s, door["mode"], door, dt_model) for s in test])
        y = np.array([r["label"] for r in rows])
        res[f"{noise} m"] = auc(y, final_scores(rows, pres))
    return res


def real_section(bundle, dt_model):
    door, pres = bundle["door"], bundle["presence"]
    out = {}
    for take in takes():
        s = real_session(take)
        r = run_door(s, door["mode"], door, dt_model)
        rows = score_rows(student_rows(s, r), pres)
        gt = sorted(x["appear_s"] for x in load_ground_truth(take) if x["event"] == "enter_class")
        entries = [c["t"] for c in s["crossings"] if c["direction"] == "in"]
        hit, errs = set(), []
        for g in gt:
            cand = [i for i, t in enumerate(entries) if i not in hit and abs(t - g) <= 2.5]
            if cand:
                i = min(cand, key=lambda i: abs(entries[i] - g))
                hit.add(i)
                errs.append(round(entries[i] - g, 2))
        names = {f"{t['cam_id']}:{t['track_id']}": t.get("name") for t in s["trajectories"]}
        agree = [names.get(m["track_id"]) == m["student_id"] for m in r["matches"] if names.get(m["track_id"])]
        out[take] = {"duration_s": s["recorded_s"], "scored_as_class_s": s["duration"], "check_ins": len(r["check_ins"]),
                     "entries_detected": len(entries),
                     "exits_detected": sum(c["direction"] == "out" for c in s["crossings"]),
                     "ground_truth_entries": gt,
                     "entries_within_2_5s": f"{len(errs)}/{len(gt)}" if gt else None,
                     "entry_time_errors_s": errs,
                     "matches": [(m["student_id"], m["track_id"], m["dt"]) for m in r["matches"]],
                     "agrees_with_link_names": f"{sum(agree)}/{len(agree)}" if agree else None,
                     "alerts": [(a["code"], round(a["t"], 1), a["score"], a["reason"]) for a in r["alerts"]],
                     "suppressed_alerts": len(r["suppressed"]),
                     "students": [(x["student_id"], x["score"], x["flagged"], x["reasons"]) for x in rows]}
    return out


def plots(rows, sel, bundle, test_door):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.metrics import roc_curve
    except ImportError:
        return ["matplotlib not installed: no figures"]
    OUT.mkdir(parents=True, exist_ok=True)
    pres = bundle["presence"]
    y = np.array([r["label"] for r in rows])
    X = matrix(rows, pres["medians"])
    fig, ax = plt.subplots(figsize=(5, 4))
    for m in pres["models"]:
        fpr, tpr, _ = roc_curve(y, final_scores(rows, pres, m))
        ax.plot(fpr, tpr, label=f"{m} + rules (AUC {auc(y, final_scores(rows, pres, m))})")
        fpr, tpr, _ = roc_curve(y, ml_scores(X, pres, m))
        ax.plot(fpr, tpr, "--", lw=1, label=f"{m} only (AUC {auc(y, ml_scores(X, pres, m))})")
    ax.plot([0, 1], [0, 1], color="grey", lw=0.5)
    ax.set(xlabel="false positive rate", ylabel="true positive rate", title="Presence verification (simulated test)")
    ax.legend(fontsize=6)
    fig.savefig(OUT / "presence_roc.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(5, 3))
    modes = ["window", "dt", "clf"]
    for k, key in enumerate(("entry_alerts", "D3")):
        ax.bar(np.arange(3) + k * 0.35, [test_door[m][key]["f1"] for m in modes], 0.35, label=key)
    ax.set_xticks(np.arange(3) + 0.17, ["fixed window", "dt + Hungarian", "pair classifier"])
    ax.set(ylabel="F1", title="Door audit (simulated test)")
    ax.legend()
    fig.savefig(OUT / "door_f1.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return ["presence_roc.png", "door_f1.png"]


def markdown(rep):
    d, p, r = rep["door"], rep["presence"], rep["real"]
    L = ["# Presence verification + door audit: evaluation", "",
         f"Generated {rep['created']} by `evaluate.py` from `{MODEL_FILE.name}` (trained {rep['model_created']}).",
         f"Simulated test set: {rep['test_sessions']} sessions (seed {SEEDS['test']}).", "",
         "## Door audit (simulated test)", "",
         "| Method | Entry alerts P / R / F1 | D3 P / R / F1 | Match accuracy |", "| --- | --- | --- | --- |"]
    names = {"window": "Fixed window 0-15 s (link_names-style rule)", "dt": "dt model + Hungarian",
             "clf": "Pair classifier + Hungarian"}
    for m in ("window", "dt", "clf"):
        e, x = d[m]["entry_alerts"], d[m]["D3"]
        L.append(f"| {names[m]}{' (selected)' if m == rep['door_mode'] else ''} | {e['precision']} / {e['recall']} / "
                 f"{e['f1']} | {x['precision']} / {x['recall']} / {x['f1']} | {d[m]['match_accuracy']} |")
    L += ["", "Mean F1 under camera clock jitter (sigma of noise added to crossing times):", "",
          "| sigma | " + " | ".join(names[m] for m in ("window", "dt", "clf")) + " |", "| --- | --- | --- | --- |"]
    for s, v in d["clock_jitter_mean_f1"].items():
        L.append(f"| {s} s | {v['window']} | {v['dt']} | {v['clf']} |")
    L += ["", "## Presence verification (simulated test)", "",
          f"{p['rows']} student rows, {p['anomalies']} anomalous. Flag threshold {rep['threshold']} (chosen on val).", "",
          "| Model | AUC (model only) | AUC (with rules) | P / R / F1 at threshold |", "| --- | --- | --- | --- |"]
    for m, v in p["models"].items():
        L.append(f"| {m}{' (selected)' if m == rep['selected'] else ''} | {v.get('auc_model_only', '-')} | {v['auc']} | "
                 f"{v['precision']} / {v['recall']} / {v['f1']} |")
    L += ["", "Recall per anomaly type (rules alone vs the selected model + rules):", "",
          "| Type | n | Rules | Model + rules |", "| --- | --- | --- | --- |"]
    for t, v in p["recall_by_type"].items():
        L.append(f"| {t} | {v['n']} | {v['rules']} | {v['selected_model']} |")
    L += ["", f"False alarm rate on normal students: rules {p['false_alarm_rate']['rules']}, "
              f"model + rules {p['false_alarm_rate']['selected_model']}.", "",
          "Ablation (logistic regression retrained without a feature group, test AUC): " +
          ", ".join(f"{k} {v}" for k, v in p["ablation_logreg_auc"].items()) + ".", "",
          "Robustness to map-coordinate noise (selected model, test AUC): " +
          ", ".join(f"{k} {v}" for k, v in rep["noise_auc"].items()) + ".", "",
          "## Recorded takes (all normal: no fraud was recorded yet)", "",
          "Each take is scored as the first seconds of a 90-minute class (`sessions.CLASS_S`): the takes only film "
          "people arriving, and whoever is not seen walking out is still in class.", "",
          "| Take | Length | Check-ins | Entries found | GT entries within 2.5 s | Agrees with link_names | Alerts | Flagged students |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for t, v in r.items():
        flagged = [s for s, _, f, _ in v["students"] if f]
        L.append(f"| {t} | {v['duration_s']} s | {v['check_ins']} | {v['entries_detected']} | "
                 f"{v['entries_within_2_5s'] or '-'} | {v['agrees_with_link_names'] or '-'} | "
                 f"{'; '.join(f'{c} at {tt} s' for c, tt, _, _ in v['alerts']) or 'none'} | {', '.join(flagged) or 'none'} |")
    L += ["", "Takes 2, 5, 6 and 7 have no recognised check-in (the attendance camera did not name anyone), so every "
              "entry there is reported as D1. Whether that is right depends on the scenario of those takes, which is "
              "not written down yet (`data/video_config.json`: \"TBC\")."]
    return "\n".join(L) + "\n"


def main(quick=False):
    import joblib
    from datetime import datetime
    t0 = time.time()
    if not MODEL_FILE.is_file():
        raise SystemExit(f"{MODEL_FILE.name} not found: run train.py first")
    bundle = joblib.load(MODEL_FILE)
    dt_model = DtModel.from_dict(bundle["dt_model"])
    n_test = 120 if quick else 500
    test = simulate(n_test, SEEDS["test"], dt_model)
    train = simulate(bundle["sizes"]["train"], SEEDS["train"], dt_model)       # same as train.py (same seed)
    train_rows = presence_data(train, [run_door(s, bundle["door"]["mode"], bundle["door"], dt_model) for s in train])
    rep = {"created": datetime.now().isoformat(timespec="seconds"), "model_created": bundle["created"],
           "test_sessions": n_test, "door_mode": bundle["door"]["mode"],
           "selected": bundle["presence"]["selected"], "threshold": bundle["presence"]["threshold"]}
    rep["door"] = door_section(test, bundle, dt_model)
    print(f"door audit done ({time.time() - t0:.0f} s)")
    rep["presence"], rows, sel = presence_section(test, bundle, dt_model, train_rows)
    print(f"presence done ({time.time() - t0:.0f} s)")
    rep["noise_auc"] = noise_section(bundle, dt_model, n_test // 2, train_rows)
    rep["real"] = real_section(bundle, dt_model)
    rep["figures"] = plots(rows, sel, bundle, rep["door"])
    write_json(OUT / "report.json", rep)
    (OUT / "report.md").write_text(markdown(rep), encoding="utf-8")
    print(f"wrote outputs/eval/report.md, report.json ({time.time() - t0:.0f} s)")
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    main(ap.parse_args().quick)
