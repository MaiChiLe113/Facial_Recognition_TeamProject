"""Train both features and save ml/presence_verification/presence_verification.joblib.  Owner: Đức Mạnh

    .venv/Scripts/python ml/presence_verification/train.py            # ~2-4 min on a laptop CPU
    .venv/Scripts/python ml/presence_verification/train.py --quick    # small sets, for a smoke test

Steps
1. dt model: fitted on the real takes (ground truth of take 1 and 3, link_names names of the others).
2. Simulated sessions (train / val; test is made separately by evaluate.py, other seed).
3. Door audit: tune the "unmatched" cost of the dt mode on val; train the logistic-regression pair
   classifier on train and tune its cost; keep the mode with the better val F1.
4. Presence: rows from the selected door mode; IsolationForest (normal rows only), LogisticRegression and
   RandomForest (labelled rows); keep the model with the best val ROC-AUC; pick the flag threshold on val.
"""
import argparse
import json
import time
from datetime import datetime

import numpy as np

from door_audit import DtModel, PAIR_FEATURES
from presence import FEATURES, RULES, matrix
from pv_common import MODEL_FILE, OUTPUTS, write_json
from pv_metrics import (auc, best_threshold, door_scores, pair_training_data, presence_data, run_door)
from sessions import real_dt_samples
from simulate import simulate

SEEDS = {"train": 1, "val": 2, "test": 3}
RULE_FLOOR = 0.8     # a fired rule puts the score at least this high


def fit_presence_models(train_rows, seed=0):
    from sklearn.ensemble import IsolationForest, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    X = matrix(train_rows)
    medians = np.nanmedian(X, axis=0)
    medians = np.where(np.isnan(medians), 0.0, medians)
    X = matrix(train_rows, medians)
    y = np.array([r["label"] for r in train_rows])
    normal = X[y == 0]
    iforest = IsolationForest(n_estimators=300, contamination="auto", random_state=seed).fit(normal)
    raw = -iforest.score_samples(X)
    logreg = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")).fit(X, y)
    rf = RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced_subsample",
                                random_state=seed, n_jobs=-1).fit(X, y)
    return {"feature_names": FEATURES, "medians": medians.tolist(),
            "normal_mean": normal.mean(axis=0).tolist(), "normal_std": normal.std(axis=0).tolist(),
            "iforest_range": [float(np.percentile(raw, 1)), float(np.percentile(raw, 99))],
            "models": {"iforest": iforest, "logreg": logreg, "rf": rf}, "rules": dict(RULES),
            "rule_floor": RULE_FLOOR}


def final_scores(rows, presence, which=None):
    from presence import ml_scores
    s = ml_scores(matrix(rows, presence["medians"]), presence, which)
    return np.array([max(v, presence["rule_floor"] if r["rules"] else 0.0) for v, r in zip(s, rows)])


def main(quick=False):
    t0 = time.time()
    n_train, n_val = (120, 60) if quick else (900, 250)
    report = {"created": datetime.now().isoformat(timespec="seconds")}

    # 1. dt model from the real takes
    dts = real_dt_samples()
    dt_model = DtModel.fit([d for _, _, d in dts])
    report["dt_model"] = {**dt_model.to_dict(), "samples": dts}
    print(f"dt model from {len(dts)} real samples: median {dt_model.median():.1f} s, "
          f"sigma {dt_model.sigma:.2f}  ({[d for _, _, d in dts]})")

    # 2. simulated sessions
    train = simulate(n_train, SEEDS["train"], dt_model)
    val = simulate(n_val, SEEDS["val"], dt_model)
    print(f"simulated {len(train)} train + {len(val)} val sessions ({time.time() - t0:.0f} s)")

    # 3. door audit
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    door = {"u_dt": 4.0, "u_clf": 1.0, "min_score_dt": 0.0, "min_score_clf": 0.0, "pair_clf": None,
            "pair_features": PAIR_FEATURES}
    Xp, yp = pair_training_data(train, dt_model)
    door["pair_clf"] = make_pipeline(StandardScaler(),
                                     LogisticRegression(max_iter=2000, class_weight="balanced")).fit(Xp, yp)
    grids = {"dt": [2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0], "clf": [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]}
    tune = {}
    for mode, grid in grids.items():      # joint grid: unmatched cost x minimum alert score
        best = (None, None, -1.0)
        for u in grid:
            door[f"u_{mode}"] = u
            door[f"min_score_{mode}"] = 0.0
            results = [run_door(s, mode, door, dt_model) for s in val]
            for ms in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
                kept = [{**r, "alerts": [a for a in r["alerts"] if a["score"] >= ms]} for r in results]
                f = door_scores(val, kept)["mean_f1"]
                tune[f"{mode} u={u} min_score={ms}"] = f
                if f > best[2]:
                    best = (u, ms, f)
        door[f"u_{mode}"], door[f"min_score_{mode}"] = best[0], best[1]
    tune_dt = {k: v for k, v in tune.items() if k.startswith("dt")}
    tune_clf = {k: v for k, v in tune.items() if k.startswith("clf")}
    val_door = {m: door_scores(val, [run_door(s, m, door, dt_model) for s in val]) for m in ("window", "dt", "clf")}
    door["mode"] = "clf" if val_door["clf"]["mean_f1"] >= val_door["dt"]["mean_f1"] else "dt"
    report["door"] = {"grid_dt": tune_dt, "grid_clf": tune_clf, "u_dt": door["u_dt"], "u_clf": door["u_clf"],
                      "min_score_dt": door["min_score_dt"], "min_score_clf": door["min_score_clf"],
                      "mode": door["mode"], "pair_training": {"pairs": int(len(yp)), "positives": int(yp.sum())},
                      "val": val_door}
    print(f"door audit: mode {door['mode']}, val mean F1 window {val_door['window']['mean_f1']} | "
          f"dt {val_door['dt']['mean_f1']} | clf {val_door['clf']['mean_f1']} ({time.time() - t0:.0f} s)")

    # 4. presence verification
    tr_rows = presence_data(train, [run_door(s, door["mode"], door, dt_model) for s in train])
    va_rows = presence_data(val, [run_door(s, door["mode"], door, dt_model) for s in val])
    presence = fit_presence_models(tr_rows)
    y_val = np.array([r["label"] for r in va_rows])
    val_auc = {m: auc(y_val, final_scores(va_rows, presence, m)) for m in presence["models"]}
    val_auc_ml_only = {}
    from presence import ml_scores
    for m in presence["models"]:
        val_auc_ml_only[m] = auc(y_val, ml_scores(matrix(va_rows, presence["medians"]), presence, m))
    presence["selected"] = max(val_auc, key=lambda m: val_auc[m] or 0)
    thr, f1 = best_threshold(y_val, final_scores(va_rows, presence))
    presence["threshold"] = thr
    report["presence"] = {"rows": {"train": len(tr_rows), "val": len(va_rows),
                                   "train_anomalies": int(sum(r["label"] for r in tr_rows))},
                          "val_auc_with_rules": val_auc, "val_auc_model_only": val_auc_ml_only,
                          "selected": presence["selected"], "threshold": thr, "val_f1": f1}
    print(f"presence: val AUC {val_auc} -> {presence['selected']}, threshold {thr} (val F1 {f1}) "
          f"({time.time() - t0:.0f} s)")

    import joblib
    import sklearn
    bundle = {"version": 1, "created": report["created"], "dt_model": dt_model.to_dict(), "door": door,
              "presence": presence, "quick": quick, "sklearn": sklearn.__version__,
              "seeds": SEEDS, "sizes": {"train": n_train, "val": n_val}}
    joblib.dump(bundle, MODEL_FILE)
    report["model_file"] = MODEL_FILE.name
    report["seconds"] = round(time.time() - t0, 1)
    write_json(OUTPUTS / "train_report.json", json.loads(json.dumps(report, default=str)))
    print(f"saved {MODEL_FILE.name} and outputs/train_report.json in {report['seconds']} s")
    return bundle


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small simulated sets (smoke test, worse model)")
    main(ap.parse_args().quick)
