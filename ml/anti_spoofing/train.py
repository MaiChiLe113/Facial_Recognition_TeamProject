"""Train the MobileNetV2 liveness classifier (run on Kaggle / Colab GPU).

Example (Kaggle, LCC-FASD attached as a dataset):

    python train.py --data-root /kaggle/input/lcc-fasd --epochs 10 \
        --out weights/liveness_mobilenetv2.pt --results results/antispoof

Own webcam samples (printed photo / phone replay) can be mixed in:

    --extra-train own_data/train   --extra-dev own_data/dev

where each folder has real/ and spoof/ sub-folders. Split own data BY PERSON
(e.g. 3 people for train, 2 for dev) so the model is not tested on faces it saw.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from data import (FaceLivenessDataset, balanced_sampler, describe, eval_transform,
                  find_split_dir, scan_split, train_transform)
from metrics import auc, choose_threshold, predict_scores, rates
from model import build_model, save_checkpoint, set_train_mode


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", help="folder holding the train/dev/eval split folders")
    ap.add_argument("--train-dir")
    ap.add_argument("--dev-dir")
    ap.add_argument("--extra-train", help="own data for training (real/ + spoof/)")
    ap.add_argument("--extra-dev", help="own data added to the dev set")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--freeze-until", type=int, default=14, help="freeze MobileNetV2 blocks [0, N)")
    ap.add_argument("--threshold-mode", choices=["eer", "apcer1"], default="eer",
                    help="eer: APCER=BPCER; apcer1: APCER<=1%% (stricter against attacks)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0, help="debug: cap images per split")
    ap.add_argument("--no-pretrained", action="store_true", help="debug only (no ImageNet download)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="weights/liveness_mobilenetv2.pt")
    ap.add_argument("--results", default="results/antispoof")
    return ap.parse_args()


def load_samples(path, limit):
    s = scan_split(path)
    if limit:
        random.Random(0).shuffle(s)
        s = s[:limit]
    return s


def main():
    a = parse_args()
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("device:", device)

    train_dir = a.train_dir or (find_split_dir(a.data_root, ("train",)) if a.data_root else None)
    dev_dir = a.dev_dir or (find_split_dir(a.data_root, ("dev", "val")) if a.data_root else None)
    if not train_dir or not dev_dir:
        raise SystemExit("Could not find train/dev folders: pass --data-root or --train-dir/--dev-dir")
    print("train:", train_dir, "\ndev:  ", dev_dir)

    train_s = load_samples(train_dir, a.limit)
    dev_s = load_samples(dev_dir, a.limit)
    if a.extra_train:
        train_s += scan_split(a.extra_train)
    if a.extra_dev:
        dev_s += scan_split(a.extra_dev)
    describe("train", train_s); describe("dev", dev_s)
    if not train_s or not dev_s:
        raise SystemExit("No images found. Check folder names (real/ and spoof/ or fake/).")

    train_dl = DataLoader(FaceLivenessDataset(train_s, train_transform()), batch_size=a.batch_size,
                          sampler=balanced_sampler(train_s), num_workers=a.workers,
                          pin_memory=device == "cuda", drop_last=len(train_s) > a.batch_size)
    dev_dl = DataLoader(FaceLivenessDataset(dev_s, eval_transform()), batch_size=a.batch_size,
                        shuffle=False, num_workers=a.workers)

    model = build_model(pretrained=not a.no_pretrained, freeze_until=a.freeze_until).to(device)
    params = [p for p in model.parameters() if p.requires_grad]
    n_train = sum(p.numel() for p in params)
    print(f"trainable params: {n_train:,} / {sum(p.numel() for p in model.parameters()):,}")
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=a.weight_decay)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=a.epochs)
    loss_fn = nn.BCEWithLogitsLoss()  # classes are balanced by the sampler
    scaler = torch.amp.GradScaler("cuda", enabled=device == "cuda")

    out, res = Path(a.out), Path(a.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    res.mkdir(parents=True, exist_ok=True)

    history, best_auc, best_state = [], -1.0, None
    for epoch in range(1, a.epochs + 1):
        t0 = time.time()
        set_train_mode(model, a.freeze_until)
        total, n = 0.0, 0
        for x, y in train_dl:
            x, y = x.to(device), y.float().to(device)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device, enabled=device == "cuda"):
                loss = loss_fn(model(x).squeeze(1), y)
            scaler.scale(loss).backward()
            scaler.step(opt); scaler.update()
            total += loss.item() * len(y); n += len(y)
        sched.step()

        yd, sd = predict_scores(model, dev_dl, device)
        dev_auc = auc(yd, sd)
        r = rates(yd, sd, 0.5)
        row = {"epoch": epoch, "train_loss": total / max(n, 1), "dev_auc": dev_auc,
               "dev_acc@0.5": r["accuracy"], "dev_apcer@0.5": r["apcer"], "dev_bpcer@0.5": r["bpcer"]}
        history.append(row)
        print(f"epoch {epoch:>2}/{a.epochs} loss {row['train_loss']:.4f} | dev AUC {dev_auc:.4f} "
              f"acc {r['accuracy']:.3f} APCER {r['apcer']:.3f} BPCER {r['bpcer']:.3f} ({time.time() - t0:.0f}s)")
        if dev_auc > best_auc:
            best_auc = dev_auc
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    # Restore the best epoch, pick the decision threshold on DEV (never on the eval split).
    model.load_state_dict(best_state)
    yd, sd = predict_scores(model, dev_dl, device)
    thr = choose_threshold(yd, sd, a.threshold_mode)
    print(f"\nbest dev AUC {best_auc:.4f} | threshold ({a.threshold_mode}) = {thr:.4f} | "
          f"dev rates: {rates(yd, sd, thr)}")

    save_checkpoint(out, model, thr, {"dev_auc": best_auc, "threshold_mode": a.threshold_mode,
                                      "freeze_until": a.freeze_until, "epochs": a.epochs,
                                      "lr": a.lr, "batch_size": a.batch_size,
                                      "n_train": len(train_s), "n_dev": len(dev_s)})
    (res / "history.json").write_text(json.dumps(history, indent=2))
    plot_history(history, res / "training_curves.png")
    print("saved:", out, "and", res / "history.json")


def plot_history(history, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ep = [h["epoch"] for h in history]
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.5))
    ax[0].plot(ep, [h["train_loss"] for h in history], marker="o")
    ax[0].set(title="Train loss", xlabel="epoch")
    ax[1].plot(ep, [h["dev_auc"] for h in history], marker="o", color="tab:green")
    ax[1].set(title="Dev AUC", xlabel="epoch")
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
