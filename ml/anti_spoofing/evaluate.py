"""Evaluate a trained liveness checkpoint and write the numbers/plots for the report.

    python evaluate.py --data-root /kaggle/input/lcc-fasd \
        --weights ml/anti_spoofing/anti_spoofing.pt --results results/antispoof

The decision threshold stored in the checkpoint was chosen on the DEV split, so the
eval numbers here are an honest estimate. Add --extra-eval own_data/test to also report
our own webcam spoofs (printed photo / phone replay) separately.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from data import FaceLivenessDataset, describe, eval_transform, find_split_dir, scan_split
from metrics import auc, predict_scores, rates
from model import load_checkpoint


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root")
    ap.add_argument("--eval-dir")
    ap.add_argument("--extra-eval", help="our own webcam data (real/ + spoof/), reported separately")
    ap.add_argument("--weights", default="ml/anti_spoofing/anti_spoofing.pt")
    ap.add_argument("--results", default="results/antispoof")
    ap.add_argument("--threshold", type=float, help="override the threshold saved in the checkpoint")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    return ap.parse_args()


def run_split(name, samples, model, device, thr, a, res):
    describe(name, samples)
    dl = DataLoader(FaceLivenessDataset(samples, eval_transform()), batch_size=a.batch_size,
                    shuffle=False, num_workers=a.workers)
    y, s = predict_scores(model, dl, device)
    out = {"n": int(len(y)), "threshold": thr, "auc": auc(y, s), **rates(y, s, thr)}
    pred = s >= thr
    out["confusion"] = {  # rows = truth, cols = prediction
        "live->live": int(((y == 1) & pred).sum()), "live->spoof": int(((y == 1) & ~pred).sum()),
        "spoof->live": int(((y == 0) & pred).sum()), "spoof->spoof": int(((y == 0) & ~pred).sum()),
    }
    plot_roc(y, s, thr, res / f"roc_{name}.png", name)
    print(json.dumps(out, indent=2))
    return out


def plot_roc(y, s, thr, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import roc_curve

    fpr, tpr, _ = roc_curve(y, s)
    r = rates(y, s, thr)
    fig, ax = plt.subplots(figsize=(4.5, 4.2))
    ax.plot(fpr, tpr, label=f"AUC = {auc(y, s):.4f}")
    ax.scatter([r["apcer"]], [1 - r["bpcer"]], color="red", zorder=3, label=f"threshold {thr:.2f}")
    ax.plot([0, 1], [0, 1], "k--", lw=0.8)
    ax.set(xlabel="APCER (spoof accepted)", ylabel="1 - BPCER (live accepted)", title=f"ROC: {title}")
    ax.legend(loc="lower right"); fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def main():
    a = parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, ckpt = load_checkpoint(a.weights, device)
    thr = a.threshold if a.threshold is not None else ckpt["threshold"]
    res = Path(a.results); res.mkdir(parents=True, exist_ok=True)

    eval_dir = a.eval_dir or (find_split_dir(a.data_root, ("eval", "test")) if a.data_root else None)
    if not eval_dir:
        raise SystemExit("Pass --data-root or --eval-dir")
    samples = scan_split(eval_dir)
    if a.limit:
        samples = samples[: a.limit]

    report = {"weights": a.weights, "checkpoint_meta": ckpt.get("meta", {})}
    report["eval"] = run_split("eval", samples, model, device, thr, a, res)
    if a.extra_eval:
        report["own_webcam"] = run_split("own_webcam", scan_split(a.extra_eval), model, device, thr, a, res)

    (res / "metrics.json").write_text(json.dumps(report, indent=2))
    print("saved:", res / "metrics.json")


if __name__ == "__main__":
    main()
