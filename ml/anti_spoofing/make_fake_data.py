"""Make a tiny FAKE dataset to check that train.py / evaluate.py / liveness.py run end to end.

    python ml/anti_spoofing/make_fake_data.py fake_lcc

Creates fake_lcc/{train,dev,eval}/{real,spoof}/*.png with random images. The images mean
nothing, so the accuracy is meaningless: this only tests the code, not the model.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

root = Path(sys.argv[1] if len(sys.argv) > 1 else "fake_lcc")
rng = np.random.default_rng(0)
for split, n in (("train", 40), ("dev", 20), ("eval", 20)):
    for label, bright in (("real", 150), ("spoof", 100)):
        d = root / split / label
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            arr = np.clip(rng.normal(bright, 40, (96, 96, 3)), 0, 255).astype("uint8")
            Image.fromarray(arr).save(d / f"{i}.png")
print("created", root.resolve())
