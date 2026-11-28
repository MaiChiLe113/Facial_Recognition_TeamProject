"""Fine-tune the anti-spoofing model on the team's own photos (real faces vs faces shown on a phone screen).

    HAWKEYE_DRIVE_ROOT=data python ml/anti_spoofing/finetune_team.py            # cross-validate, then train on all
    HAWKEYE_DRIVE_ROOT=data python ml/anti_spoofing/finetune_team.py --cv-only  # numbers only, writes nothing

Writes ml/anti_spoofing/anti_spoofing_v2.pt (same format as anti_spoofing.pt; it does NOT replace it). Use it with
HAWKEYE_ANTI_SPOOFING_WEIGHTS=ml/anti_spoofing/anti_spoofing_v2.pt, or copy it over anti_spoofing.pt.

Data (cut with the pipeline's YuNet detector and the same 25 % margin as the app):
  spoof  data/AppliedML/Hồng Minh/1795836404*.jpg   a phone screen showing a face (whole photo = one phone face)
         data/AppliedML/Hồng Minh/1795842868*.jpg   phone screens (Instagram: other people, dark UI); every face found
                                                    in the photo is on the screen, avatars and icons included
         data/AppliedML/Hồng Minh/fake_image*.jpg   the smaller face (the phone) in each photo
  real   every other photo in the five people's folders (masks, hoods, glasses and profiles included, they are live),
         plus the big face in fake_image*.jpg
Cross-validation holds out contiguous blocks of photos (neighbouring photos are near-duplicates).
All spoofs come from one person and one setting: treat the numbers as optimistic.
"""
import argparse
import copy
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms as T
from torchvision.models import mobilenet_v2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
from app.core.ml_models import crop_face  # noqa: E402
from app.pipeline.detector import detect_faces  # noqa: E402
from app.services import gallery as G  # noqa: E402

SRC = Path(__file__).parent / "anti_spoofing.pt"
OUT = Path(__file__).parent / "anti_spoofing_v2.pt"
FOLDS, EPOCHS, LR, BATCH, FREEZE_UNTIL = 4, 6, 1e-4, 16, 14
THRESHOLD = 0.4   # held-out: ~19 % of spoofs accepted (mostly tiny avatars), ~12 % of live frames rejected; see the table
SKIP = {"student_card_image", "video data"}
PHONE_PREFIXES = ("fake", "1795836404", "1795842868")   # photos of a phone screen: never real data


def largest_face(img, relaxed=True):
    for conf in (0.8, 0.5) if relaxed else (0.8,):
        faces = detect_faces(img, conf=conf, min_size=24)
        if faces:
            return faces[0]
    return None


def load_samples(root):
    """[(PIL crop RGB, label 1=live/0=spoof, group)]"""
    out = []

    def add(img, box, y, group):
        crop = crop_face(img, box, "anti_spoofing")
        if crop is not None:
            out.append((Image.fromarray(np.ascontiguousarray(crop[:, :, ::-1])), y, group))

    for person in sorted(d for d in (root / "AppliedML").iterdir() if d.is_dir() and d.name not in SKIP):
        files = sorted(p for p in person.iterdir() if p.suffix.lower() in G.IMAGE_EXT and p.name != "desktop.ini")
        real_files = [f for f in files if not f.name.startswith(PHONE_PREFIXES)]
        for i, f in enumerate(real_files):
            img = G._read_photo(f)
            box = largest_face(img)
            if box is not None:
                add(img, box, 1, f"{person.name}-real-{i * FOLDS // len(real_files)}")
        if person.name == "Hồng Minh":
            for f in files:
                if not f.name.startswith(PHONE_PREFIXES):
                    continue
                img = G._read_photo(f)
                if f.name.startswith("fake"):
                    faces = detect_faces(img, conf=0.5, min_size=24)
                    if len(faces) < 2:
                        faces = detect_faces(img, conf=0.8, min_size=24)
                    big, phone = faces[0], next((b for b in faces[1:] if b[2] >= 80), None)
                    add(img, big, 1, f"{person.name}-real-fake")
                    if phone is not None or len(faces) == 1:
                        add(img, phone if phone is not None else faces[0], 0, f"{f.stem}")
                elif f.name.startswith("1795842868"):
                    for box in detect_faces(img, conf=0.5, min_size=24):     # all of them are on the screen
                        add(img, box, 0, f.stem)
                else:
                    box = largest_face(img, relaxed=False)
                    if box is not None:
                        add(img, box, 0, f.stem)
    return out


MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)


def tfs(size, train):
    base = [T.Resize((size, size), interpolation=T.InterpolationMode.BILINEAR)]
    if train:
        base += [T.RandomHorizontalFlip(), T.RandomAffine(degrees=15, translate=(0.06, 0.06), scale=(0.9, 1.15)),
                 T.ColorJitter(0.35, 0.3, 0.15, 0.03)]
    return T.Compose(base + [T.ToTensor(), T.Normalize(MEAN, STD)])


def build(ckpt):
    m = mobilenet_v2(weights=None)
    m.classifier = nn.Sequential(nn.Dropout(0.2), nn.Linear(m.classifier[1].in_features, 1))
    m.load_state_dict(ckpt["state_dict"])
    return m


@torch.inference_mode()
def scores(model, samples, size):
    model.eval()
    tf = tfs(size, False)
    if not samples:
        return np.array([])
    x = torch.stack([tf(s[0]) for s in samples])
    return torch.sigmoid(model(x).squeeze(1)).numpy()


def train(model, samples, size, seed=0):
    random.seed(seed); torch.manual_seed(seed); np.random.seed(seed)
    for i, block in enumerate(model.features):
        for p in block.parameters():
            p.requires_grad = i >= FREEZE_UNTIL
    tf = tfs(size, True)
    ys = np.array([s[1] for s in samples])
    w = np.where(ys == 1, 0.5 / max(1, (ys == 1).sum()), 0.5 / max(1, (ys == 0).sum()))   # live and spoof equally often
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR, weight_decay=1e-3)
    steps = EPOCHS * max(1, len(samples) // BATCH)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    loss_fn = nn.BCEWithLogitsLoss()
    for _ in range(steps):
        model.train()
        idx = np.random.choice(len(samples), BATCH, p=w / w.sum())
        x = torch.stack([tf(samples[i][0]) for i in idx])
        y = torch.tensor([float(samples[i][1]) for i in idx])
        loss = loss_fn(model(x).squeeze(1), y)
        opt.zero_grad(); loss.backward(); opt.step(); sched.step()
    return model.eval()


def auc(pos, neg):
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg])) if len(pos) and len(neg) else float("nan")


def best_threshold(live, spoof):
    """Smallest APCER + BPCER (spoof accepted + live rejected) over candidate cut-offs."""
    cands = np.unique(np.concatenate([live, spoof, [0.5]]))
    cost = [(spoof >= t).mean() + (live < t).mean() for t in cands]
    return float(cands[int(np.argmin(cost))])


def report(tag, live, spoof, thr):
    print(f"[{tag}] live n={len(live)} spoof n={len(spoof)} AUC {auc(live, spoof):.3f} | at {thr:.3f}: "
          f"spoof accepted {(spoof >= thr).mean():.2f}  live rejected {(live < thr).mean():.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv-only", action="store_true")
    args = ap.parse_args()
    ckpt = torch.load(SRC, map_location="cpu", weights_only=True)
    size = int(ckpt.get("img_size", 224))
    samples = load_samples(G._enrolment_root())
    ys = np.array([s[1] for s in samples])
    print(f"samples: live {int((ys == 1).sum())}, spoof {int((ys == 0).sum())}")

    # folds: contiguous blocks of the spoofs, and of each person's real photos
    fold = np.zeros(len(samples), int)
    spoof_idx = [i for i, s in enumerate(samples) if s[1] == 0]
    for n, i in enumerate(spoof_idx):
        fold[i] = n * FOLDS // len(spoof_idx)                       # contiguous blocks
    for g in sorted({s[2] for s in samples if s[1] == 1}):
        members = [i for i, s in enumerate(samples) if s[2] == g]
        for n, i in enumerate(members):
            fold[i] = n * FOLDS // len(members)

    base = build(ckpt)
    held = np.zeros(len(samples)); held_v1 = scores(base, samples, size)
    for k in range(FOLDS):
        tr = [samples[i] for i in range(len(samples)) if fold[i] != k]
        te = [i for i in range(len(samples)) if fold[i] == k]
        m = train(copy.deepcopy(base), tr, size)
        held[te] = scores(m, [samples[i] for i in te], size)
        print(f"fold {k}: held-out live {sum(ys[te] == 1)} spoof {sum(ys[te] == 0)}")
    v1_thr = float(ckpt["threshold"])
    report("v1 (current)", held_v1[ys == 1], held_v1[ys == 0], v1_thr)
    thr = THRESHOLD
    print(f"EER-style cut-off would be {best_threshold(held[ys == 1], held[ys == 0]):.3f}; using {THRESHOLD}")
    report("v2 held-out", held[ys == 1], held[ys == 0], thr)
    print("v2 held-out spoof scores:", np.round(np.sort(held[ys == 0]), 3))
    for t in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
        print(f"  held-out at {t}: spoof accepted {(held[ys == 0] >= t).mean():.2f}  live rejected {(held[ys == 1] < t).mean():.2f}")
    if args.cv_only:
        return

    model = train(copy.deepcopy(base), samples, size, seed=1)
    final = scores(model, samples, size)
    report("v2 on its own training data (not a test)", final[ys == 1], final[ys == 0], thr)
    out = dict(ckpt)
    out["state_dict"] = {k: v.cpu() for k, v in model.state_dict().items()}
    out["threshold"] = thr
    torch.save(out, OUT)
    print("saved", OUT, "threshold", round(thr, 4))


if __name__ == "__main__":
    main()
