# Emotion — Owner: Minh Thành

- [x] FER2013 ([Hugging Face mirror](https://huggingface.co/datasets/Aaryan333/fer2013_train_publicTest_privateTest), the original split: train 28,709 / publicTest 3,589 / privateTest 3,589) into `data/raw/fer2013/` (git-ignored)
- [x] AffectNet subset ([Hugging Face](https://huggingface.co/datasets/Mauregato/affectnet_short), train 23,233 / val 5,809, 96×96 colour, 8 classes) into `data/raw/affectnet/` (git-ignored). Added because the FER2013 model did badly on real webcam faces, especially with glasses
- [x] `emotion_training.ipynb` — small CNN baseline, fine-tuned ResNet-18 on FER2013, fine-tuned ResNet-18 on FER2013 + AffectNet, 7 classes
- [x] Evaluation — accuracy, macro-F1, confusion matrix on both test sets (in the same notebook, plots saved to `results/emotion/` at the repo root)
- [x] Export as `emotion.pt` for `infer.py` (last notebook cell)

## Data preparation

- FER2013: used as is (48×48 grayscale).
- AffectNet: contempt dropped (FER2013 has no contempt); labels mapped to the FER2013 order. Each face is found with YuNet and cut
  as a square as tall as the face box, then made 48×48 grayscale, so training images look like webcam face crops.
  YuNet found a face in 18,825 + 2,091 train/validation images (10% of AffectNet train held out for picking the best epoch) and
  5,230 test images. AffectNet's own validation split is the test set (its official test set is not public).

## Training

| | Small CNN | ResNet-18 |
| --- | --- | --- |
| Start | From scratch | ImageNet weights; `conv1`, `bn1`, `layer1` frozen, the rest fine-tuned |
| Input | 48×48 grayscale, 0–1 | Same, enlarged to 96×96 and copied to 3 channels inside the model |
| Epochs, learning rate | 40, 1e-3 | 20, 3e-4 |
| Shared | Adam, cosine learning-rate decay, batch 128, cross-entropy loss, augmentation on the GPU (flip, ±10° rotation, ±10% shift, 0.9–1.1 zoom); the epoch with the best validation accuracy is kept | |

All three models trained on an RTX 4060 Laptop GPU in 28 minutes including data loading (env: Python 3.12, PyTorch 2.14 + CUDA 13.0, kornia).

## Results (test sets never used for training or model selection)

| Model | FER2013 accuracy | FER2013 macro F1 | AffectNet accuracy | AffectNet macro F1 |
| --- | --- | --- | --- | --- |
| Small CNN (FER2013) | 0.6662 | 0.5468 | 0.4841 | 0.3989 |
| ResNet-18 (FER2013) | 0.7058 | 0.6942 | 0.4598 | 0.3960 |
| **ResNet-18 (FER2013 + AffectNet)** | **0.7066** | **0.6975** | **0.6608** | **0.6319** |

Training on FER2013 alone does not carry over to real-world faces (46% on AffectNet). Adding AffectNet raises that to 66% with no
loss on FER2013, so the combined model is used by the app.

Combined model per emotion (F1), FER2013 / AffectNet: happy 0.893 / 0.893, surprise 0.790 / 0.598, disgust 0.729 / 0.540,
neutral 0.682 / 0.749, angry 0.657 / 0.577, sad 0.566 / 0.539, fear 0.565 / 0.528.
Plots and table are written to `results/emotion/` at the repo root (git-ignored, like `results/antispoof/`): `samples.png`, `training_curves.png`, `confusion_matrices.png`, `comparison.csv`.

## Used by the app

`infer.py` + `emotion.pt` in this folder, loaded by `backend/app/core/ml_models.py` (feature `emotion`), as for the other models.
`emotion.pt` (committed on `main`; `*.pt` is git-ignored, so it was added with `git add -f`) is exported by the last notebook cell from `weights/emotion_resnet18_combined.pt`.
`predict(face_crop)` takes the face box crop (BGR), makes it 48x48 grayscale, enlarges it to 96x96 inside the model and averages
the probabilities over the last second (`SMOOTH_SECONDS`) so the label does not flicker (`reset()` clears that). It gives 0.7055 on the FER2013
test set through the app's loader. The face box can be passed as is: with this model a square crop scores the same (0.636 vs 0.633).
About 18 ms per face on a laptop CPU. Live check: the app's Features demo page (webcam, emotion icon + label).
