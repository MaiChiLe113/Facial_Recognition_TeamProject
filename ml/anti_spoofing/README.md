# Anti-spoofing (liveness) — owner: Hồng Minh

Binary classifier: **live (1)** vs **spoof (0)** on face crops. Our own model, PyTorch,
MobileNetV2 with ImageNet weights and **partial fine-tuning** (allowed by the brief).

| File | Purpose |
|---|---|
| `model.py` | MobileNetV2 + 1-logit head, freeze/unfreeze, save/load checkpoint |
| `data.py` | scans `real/` and `spoof|fake/` folders, transforms, balanced sampler |
| `metrics.py` | AUC, APCER, BPCER, ACER, threshold selection |
| `train.py` | training loop (run on Kaggle/Colab GPU) |
| `evaluate.py` | final numbers + ROC plot for the report |

Runtime code that uses the trained model: `backend/app/pipeline/liveness.py`.

## Data

| Source | Role |
|---|---|
| LCC-FASD (Kaggle `faber24/lcc-fasd`) | main training / dev / eval (5.19 GB, ratio about 1 real : 9 fake) |
| Own webcam samples (printed photo, phone replay) | added to train/dev, and a separate own-webcam test |
| CelebA-Spoof subset | optional extra experiment only (78 GB full set, non-commercial) |

Own data layout (split **by person**, so the test never contains faces seen in training):

```
own_data/train/real/*.jpg   own_data/train/spoof/*.jpg   # e.g. 3 people
own_data/dev/real/*.jpg     own_data/dev/spoof/*.jpg     # e.g. 1 person
own_data/test/real/*.jpg    own_data/test/spoof/*.jpg    # e.g. 1 person
```

Crop faces for own data with the same detector the app uses, so crops look the same at
training time and at demo time.

## Run (Kaggle / Colab)

```bash
pip install -r requirements.txt
python train.py --data-root /kaggle/input/lcc-fasd --epochs 10 \
    --extra-train own_data/train --extra-dev own_data/dev \
    --out weights/liveness_mobilenetv2.pt --results results/antispoof
python evaluate.py --data-root /kaggle/input/lcc-fasd --extra-eval own_data/test \
    --weights weights/liveness_mobilenetv2.pt --results results/antispoof
```

Copy `weights/liveness_mobilenetv2.pt` into the repo's `weights/` folder (git-ignored), or
set `HAWKEYE_LIVENESS_WEIGHTS=<path>`. The decision threshold is stored inside the file.

## Method (for the report)

- **Backbone:** MobileNetV2, ImageNet weights; blocks 0–13 frozen, blocks 14–18 and a new
  `Dropout -> Linear(1280, 1)` head trained.
- **Loss:** binary cross-entropy on the logit.
- **Class imbalance:** weighted sampler draws live and spoof equally often.
- **Optimiser:** AdamW, lr 3e-4, cosine schedule, 10 epochs. Model chosen by best dev AUC.
- **Augmentation:** flip, rotation up to 8°, mild brightness/contrast. No blur/noise, which
  would hide the print and moiré cues.
- **Threshold:** picked on dev (equal error rate by default). Eval is only used once at the end.
- **Runtime:** mean score over the last 10 crops, live if mean >= threshold.

## Results

Trained on Colab (T4 GPU), 10 epochs, about 167 s per epoch. Best epoch chosen by dev AUC (0.9916).
Decision threshold **0.0239** (equal error rate on dev), applied unchanged to eval.

| Split | n | AUC | APCER | BPCER | ACER | Accuracy |
|---|---|---|---|---|---|---|
| Dev (LCC-FASD development) | 2,948 | 0.9916 | 0.0547 | 0.0543 | 0.0545 | about 0.945 (computed from APCER/BPCER) |
| Eval (LCC-FASD evaluation) | 7,580 | 0.9784 | 0.0640 | 0.0892 | 0.0766 | 0.9350 |
| Own webcam test | | | | | | not measured yet |

Eval has 314 live and 7,266 spoof images, so accuracy is dominated by the spoof class
(always answering "spoof" would already score about 96%). Use AUC, APCER, BPCER and ACER.
Eval confusion matrix: live->live 286, live->spoof 28, spoof->live 465, spoof->spoof 6,801.

Not tested yet: tilted faces, glasses, face masks, and the live demo with printed photos and
phone replays at the attendance cam.

Files for the report: `results/antispoof/metrics.json`, `roc_eval.png`, `training_curves.png`,
`history.json` (created by `evaluate.py` / `train.py`).
