# Gesture detection — Owner: Minh Thành

Finds every hand in front of the attendance camera and names its gesture (👍 like, ✌️ peace, ✋ palm, ✊ fist, ☝️ one, 👌 ok,
🤙 call, 🤘 rock and others: 18 gestures plus no_gesture), so the system can react to hand signals as well as faces.

- [x] HaGRID sample ([Hugging Face](https://huggingface.co/datasets/cj-mills/hagrid-sample-30k-384p), 31,833 photos, 7,973 people,
      18 gestures + no_gesture) into `data/raw/hagrid/` (git-ignored)
- [x] `gesture_training.ipynb` — hand points with MediaPipe, logistic regression vs MLP, evaluation, export
- [x] `infer.py` + `gesture.pt` — `predict(frame)`, shown on the app's Features demo page

## Method

1. **Hand points:** MediaPipe Hand Landmarker (`hand_landmarker.task`, pre-trained, used only to find the hand, like YuNet for
   faces) gives 21 points (x, y, depth) per hand. Each labelled hand in HaGRID is matched to its annotated box: 33,240 hands.
2. **Normalising:** wrist moved to (0, 0) and the hand scaled to size 1, so position and distance from the camera do not matter.
3. **Our classifier** (trained here) names the gesture from the 63 numbers. Split by person: train 22,880 / validation 4,978 /
   test 5,382 hands, nobody in two sets, so the test measures new people.

| | Logistic regression | MLP |
| --- | --- | --- |
| Model | Linear, 63 inputs → 19 classes | 63 → 256 → 128 → 19, BatchNorm, ReLU, dropout 0.3 |
| Training | lbfgs, up to 3,000 iterations | Adam 1e-3, batch 256, 60 epochs, cross-entropy; random mirror (left/right hand), ±15° rotation, 0.9–1.1 scale; best validation epoch kept |

Points cached in `data/raw/hagrid/landmarks.npz` (first run ~35 min on CPU, then seconds). Training ~1 min on an RTX 4060.

## Results (test set: people never used for training or model selection)

| Model | Accuracy | Macro F1 |
| --- | --- | --- |
| Logistic regression | 0.8805 | 0.8691 |
| **MLP** | **0.9745** | **0.9732** |

Per gesture (MLP, F1) from 0.942 (one) to 0.996 (ok); per-gesture table in the notebook.
Through `infer.py` on 300 whole photos of test people: 308 of 362 labelled hands found and named correctly; most misses are
small hands (often no_gesture, resting at the side) that MediaPipe does not find. About 25 ms per frame on a laptop CPU.
Plots and table: `results/gesture/` at the repo root (git-ignored): `confusion_matrix.png`, `comparison.csv`.

## Used by the app

`predict(frame)` takes a BGR frame and returns one `{"label", "score", "box": [x, y, w, h], "points": 21 x [x, y]}` per hand (up to 2), or `[]`.
MediaPipe hand confidence is raised from 0.5 to 0.7 (`HAND_CONFIDENCE`): at 0.5 faces were sometimes taken for hands; on 600
HaGRID photos 0.7 gave no false hands and found 489 of 599 gesture hands (0.5: 515, with 3 false hands).
In the app: tick **Gesture** on the Features demo page (`/features-demo`): every hand is drawn as a skeleton (its 21 points joined along the fingers, like MediaPipe's hand diagram) with its gesture above it; `predict()` returns the points as `points`.
The backend finds this folder through `backend/app/core/ml_models.py` (`DEMO_FEATURES` includes `gesture`, next to `glasses_detection`) and returns the hands
as `hands` in `POST /api/features-demo/infer`.
