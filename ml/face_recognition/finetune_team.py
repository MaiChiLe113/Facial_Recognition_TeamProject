"""Fine-tune the checked-in face model on the team's enrolment photos (profiles, masks, hoods, glasses).

    HAWKEYE_DRIVE_ROOT=data python ml/face_recognition/finetune_team.py            # cross-validate, then train on all
    HAWKEYE_DRIVE_ROOT=data python ml/face_recognition/finetune_team.py --cv-only  # numbers only, writes nothing

Writes ml/face_recognition/face_recognition_team.pt (same export format as face_recognition.pt; it does NOT replace
it). Use it with HAWKEYE_FACE_RECOGNITION_WEIGHTS=ml/face_recognition/face_recognition_team.pt.

Photos are cut exactly like the gallery does (backend/app/services/gallery.py). Cross-validation holds out contiguous
blocks of each person's photos (neighbouring photos are near-duplicates, so a random split would flatter the model).
Loss: batch-hard triplet on unit embeddings, a small learning rate, layer3+layer4 trainable, strong augmentation
(flip, rotation, colour, random erasing as a stand-in for masks/hoods).
"""
import argparse
import copy
import os
import random
import sqlite3
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

import infer  # noqa: E402  (ml/face_recognition/infer.py)
from app.config import student_file  # noqa: E402
from app.services import gallery as G  # noqa: E402

OUT = Path(__file__).parent / "face_recognition_team.pt"
FOLDS = 4
STEPS, P, K, LR, MARGIN = 150, 5, 6, 3e-5, 0.3


def load_crops():
    """[(student_id, fold, crop BGR)] for every enrolment photo with a face."""
    root = G._enrolment_root()
    con = sqlite3.connect(f"file:{REPO / 'data' / 'hawkeye.sqlite3'}?mode=ro", uri=True)
    rows = con.execute("select student_id_vn, photo_folder, student_card from students").fetchall()
    items = []
    for sid, folder, card in rows:
        d = student_file(folder, root) if folder else None
        files = sorted(p for p in d.iterdir() if p.suffix.lower() in G.IMAGE_EXT) if d and d.is_dir() else []
        files = [f for f in files if f.name.lower() != "desktop.ini"]
        n = len(files)
        entries = [(f, i * FOLDS // max(n, 1)) for i, f in enumerate(files)]
        if card:
            entries.append((student_file(card, root), -1))   # the card is always training data
        for f, fold in entries:
            try:
                crop = G._face_crop(G._read_photo(f))
            except Exception:  # noqa: BLE001
                crop = None
            if crop is not None:
                items.append((sid, fold, crop))
    return items


def tensor(crop, size, mean, std):
    rgb = np.ascontiguousarray(crop[:, :, ::-1])
    x = torch.from_numpy(rgb).permute(2, 0, 1)[None].float() / 255
    x = F.interpolate(x, size=size, mode="bilinear", align_corners=False, antialias=True)
    return (x - mean) / std


def augment(x):
    """x: 1x3xHxW normalised. Flip, rotate/scale, brightness/contrast, random erasing (mask / hood stand-in)."""
    if random.random() < 0.5:
        x = x.flip(3)
    angle = np.deg2rad(random.uniform(-15, 15))
    s = random.uniform(0.9, 1.1)
    theta = torch.tensor([[np.cos(angle) / s, -np.sin(angle) / s, random.uniform(-0.06, 0.06)],
                          [np.sin(angle) / s, np.cos(angle) / s, random.uniform(-0.06, 0.06)]], dtype=torch.float32)[None]
    x = F.grid_sample(x, F.affine_grid(theta, x.shape, align_corners=False), padding_mode="border", align_corners=False)
    x = x * random.uniform(0.75, 1.25) + random.uniform(-0.3, 0.3)
    if random.random() < 0.5:            # lower-face block: mask-like
        h, w = x.shape[2:]
        y0 = int(h * random.uniform(0.45, 0.6))
        x[:, :, y0:, int(w * random.uniform(0, 0.15)): int(w * random.uniform(0.85, 1))] = random.uniform(-1.5, 1.5)
    return x


def build(payload):
    from torchvision.models import resnet18
    import torch.nn as nn

    class FaceEmbedding(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = resnet18(weights=None)
            self.backbone.fc = nn.Identity()

        def forward(self, images):
            return F.normalize(self.backbone(images).float(), dim=1)

    m = FaceEmbedding()
    m.load_state_dict(payload["state_dict"], strict=True)
    return m


def train(model, items, size, mean, std, steps=STEPS, seed=0):
    random.seed(seed); torch.manual_seed(seed)
    by = {}
    for sid, _, crop in items:
        by.setdefault(sid, []).append(crop)
    ids = [s for s in by if len(by[s]) >= 2]
    for name, p in model.named_parameters():
        p.requires_grad = name.startswith(("backbone.layer3", "backbone.layer4"))
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR, weight_decay=1e-4)
    for step in range(steps):
        model.train()
        for mod in model.modules():       # tiny batches: keep BatchNorm statistics frozen
            if isinstance(mod, torch.nn.BatchNorm2d):
                mod.eval()
        chosen = random.sample(ids, min(P, len(ids)))
        xs, ys = [], []
        for j, sid in enumerate(chosen):
            for crop in random.choices(by[sid], k=K):
                xs.append(augment(tensor(crop, size, mean, std))); ys.append(j)
        x, y = torch.cat(xs), torch.tensor(ys)
        z = model(x)
        d = 1 - z @ z.T
        same = y[:, None] == y[None]
        eye = torch.eye(len(y), dtype=torch.bool)
        hardest_pos = (d * (same & ~eye)).max(1).values
        hardest_neg = (d + 10 * same).min(1).values
        loss = F.relu(hardest_pos - hardest_neg + MARGIN).mean()
        opt.zero_grad(); loss.backward(); opt.step()
    model.eval()
    return model


@torch.inference_mode()
def embed_all(model, items, size, mean, std):
    return np.stack([F.normalize(model(tensor(c, size, mean, std)), dim=1)[0].numpy() for _, _, c in items])


def centroids(E, labels):
    out = {}
    for sid in set(labels):
        c = E[[l == sid for l in labels]].mean(0)
        out[sid] = c / np.linalg.norm(c)
    return out


def evaluate(model, items, size, mean, std, folds):
    """Held-out accuracy (train folds -> gallery, held-out fold -> queries) plus genuine / impostor scores."""
    labels = [s for s, _, _ in items]
    correct = total = 0
    genuine, impostor = [], []
    for k in range(FOLDS):
        tr = [i for i, it in enumerate(items) if it[1] != k]
        te = [i for i, it in enumerate(items) if it[1] == k]
        m = train(copy.deepcopy(model), [items[i] for i in tr], size, mean, std) if folds == "ft" else model
        E = embed_all(m, items, size, mean, std)
        cents = centroids(E[tr], [labels[i] for i in tr])
        for i in te:
            sc = {s: float(c @ E[i]) for s, c in cents.items()}
            correct += max(sc, key=sc.get) == labels[i]; total += 1
            genuine.append(sc[labels[i]])
            impostor.append(max(v for s, v in sc.items() if s != labels[i]))   # best wrong identity
    return correct, total, np.array(genuine), np.array(impostor)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv-only", action="store_true")
    args = ap.parse_args()
    payload = torch.load(infer._weights_path(), map_location="cpu", weights_only=True)
    size = tuple(payload["input_size"]) if isinstance(payload["input_size"], (list, tuple)) else (payload["input_size"],) * 2
    mean = torch.tensor(payload["normalization"]["mean"]).view(1, 3, 1, 1)
    std = torch.tensor(payload["normalization"]["std"]).view(1, 3, 1, 1)
    items = load_crops()
    print("photos with a face:", len(items), {s: sum(1 for i in items if i[0] == s) for s in {i[0] for i in items}})
    base = build(payload).eval()
    cutoff = None
    for tag in ("base", "ft"):
        if tag == "base" and not args.cv_only:
            continue                      # the baseline numbers only matter when comparing (--cv-only)
        c, t, g, imp = evaluate(base, items, size, mean, std, tag)
        print(f"[{tag}] held-out top-1 {c}/{t} = {c / t:.3f}   genuine mean {g.mean():.3f}  wrong-identity mean {imp.mean():.3f}")
        if tag == "ft":                   # accept at most ~5 % of the best-wrong-identity scores seen on held-out photos
            cutoff = float(np.clip(np.percentile(imp, 95), 0.5, 0.9))
            print(f"held-out genuine accepted at {cutoff:.3f}: {(g >= cutoff).mean():.3f}")
    if args.cv_only:
        return
    model = train(build(payload), items, size, mean, std, steps=STEPS * 2)
    E = embed_all(model, items, size, mean, std)
    labels = [s for s, _, _ in items]
    print("train-set top-1 (sanity):",
          np.mean([max((float(c @ E[i]), s) for s, c in centroids(E, labels).items())[1] == labels[i] for i in range(len(items))]))
    out = dict(payload)
    out["threshold"] = cutoff
    out["state_dict"] = {k: v.cpu() for k, v in model.state_dict().items()}
    torch.save(out, OUT)
    print("saved", OUT)


if __name__ == "__main__":
    main()
