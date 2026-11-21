"""Dataset loading for liveness training.

A split folder is expected to hold sub-folders whose names say the class, e.g.

    LCC_FASD_training/real/*.png        -> label 1 (live)
    LCC_FASD_training/spoof/*.png       -> label 0 (spoof)

Any sub-folder name containing real/live/genuine is "live"; containing
spoof/fake/attack is "spoof". Folders matching neither are ignored, so check the
printed class counts when you point the script at a new dataset.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image
from torch.utils.data import Dataset, WeightedRandomSampler
from torchvision import transforms as T

from model import IMG_SIZE, MEAN, STD

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LIVE_KEYS = ("real", "live", "genuine")
SPOOF_KEYS = ("spoof", "fake", "attack")


def scan_split(root) -> list[tuple[str, int]]:
    """List (path, label) for every image under `root`. Label 1 = live, 0 = spoof."""
    root = Path(root)
    samples: list[tuple[str, int]] = []
    for p in root.rglob("*"):
        if p.suffix.lower() not in IMG_EXT:
            continue
        label = None
        for part in reversed([s.lower() for s in p.relative_to(root).parts[:-1]]):
            if any(k in part for k in LIVE_KEYS):
                label = 1
                break
            if any(k in part for k in SPOOF_KEYS):
                label = 0
                break
        if label is not None:
            samples.append((str(p), label))
    return samples


def find_split_dir(data_root, keys: tuple[str, ...], max_depth: int = 3):
    """First folder under data_root (breadth-first) whose name contains one of `keys`."""
    data_root = Path(data_root)
    queue = deque([(data_root, 0)])
    while queue:
        d, depth = queue.popleft()
        if d != data_root and any(k in d.name.lower() for k in keys):
            return d
        if depth < max_depth:
            queue.extend((c, depth + 1) for c in sorted(d.iterdir()) if c.is_dir())
    return None


def describe(name: str, samples) -> None:
    n_live = sum(1 for _, y in samples if y == 1)
    print(f"{name:<14} {len(samples):>7} images | live {n_live:>6} | spoof {len(samples) - n_live:>6}")


def train_transform():
    # Mild augmentation only: heavy blur / JPEG noise would destroy the moire and
    # print-texture cues the model needs to see.
    return T.Compose(
        [
            T.Resize((IMG_SIZE, IMG_SIZE)),
            T.RandomHorizontalFlip(),
            T.RandomRotation(8),
            T.ColorJitter(brightness=0.25, contrast=0.2, saturation=0.1),
            T.ToTensor(),
            T.Normalize(MEAN, STD),
        ]
    )


def eval_transform():
    return T.Compose([T.Resize((IMG_SIZE, IMG_SIZE)), T.ToTensor(), T.Normalize(MEAN, STD)])


class FaceLivenessDataset(Dataset):
    def __init__(self, samples, transform):
        self.samples = list(samples)
        self.transform = transform

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        path, label = self.samples[i]
        img = Image.open(path).convert("RGB")
        return self.transform(img), float(label)


def balanced_sampler(samples) -> WeightedRandomSampler:
    """Draw live and spoof images with equal probability (LCC-FASD has ~1:9 real:fake)."""
    n_live = max(1, sum(1 for _, y in samples if y == 1))
    n_spoof = max(1, len(samples) - n_live)
    weights = [1.0 / n_live if y == 1 else 1.0 / n_spoof for _, y in samples]
    return WeightedRandomSampler(weights, num_samples=len(samples), replacement=True)
