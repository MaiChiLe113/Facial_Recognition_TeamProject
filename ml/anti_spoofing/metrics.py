"""Liveness metrics. Positive class = live (label 1).

APCER = share of spoof attacks wrongly accepted as live   (security error)
BPCER = share of real faces wrongly rejected as spoof     (usability error)
ACER  = (APCER + BPCER) / 2
"""
from __future__ import annotations

import numpy as np
import torch
from sklearn.metrics import roc_auc_score, roc_curve


@torch.no_grad()
def predict_scores(model, loader, device):
    """Returns (labels, P(live)) as numpy arrays."""
    model.eval()
    ys, ps = [], []
    for x, y in loader:
        logits = model(x.to(device)).squeeze(1)
        ps.append(torch.sigmoid(logits).cpu().numpy())
        ys.append(y.numpy())
    return np.concatenate(ys).astype(int), np.concatenate(ps)


def rates(y, s, thr):
    pred_live = s >= thr
    spoof, real = (y == 0), (y == 1)
    apcer = float(pred_live[spoof].mean()) if spoof.any() else float("nan")
    bpcer = float((~pred_live[real]).mean()) if real.any() else float("nan")
    acc = float((pred_live == (y == 1)).mean())
    return {"apcer": apcer, "bpcer": bpcer, "acer": (apcer + bpcer) / 2, "accuracy": acc}


def auc(y, s) -> float:
    return float(roc_auc_score(y, s)) if len(set(y.tolist())) == 2 else float("nan")


def eer_threshold(y, s) -> float:
    """Threshold where APCER == BPCER (equal error rate)."""
    fpr, tpr, thr = roc_curve(y, s)  # fpr = APCER, 1 - tpr = BPCER
    i = int(np.argmin(np.abs(fpr - (1 - tpr))))
    return float(thr[i])


def apcer_target_threshold(y, s, target=0.01) -> float:
    """Lowest-BPCER threshold that keeps APCER <= target (security-first choice)."""
    fpr, tpr, thr = roc_curve(y, s)
    ok = np.where(fpr <= target)[0]
    return float(thr[ok[-1]])  # fpr increases with index, so the last ok index has max tpr


def choose_threshold(y, s, mode: str) -> float:
    thr = eer_threshold(y, s) if mode == "eer" else apcer_target_threshold(y, s, 0.01)
    return min(thr, 1.0)  # roc_curve may return inf for the first point
