# Face quality + AI enrolment scan: full record

Owner: Đức Mạnh. This is his graded **individual innovative feature** (assignment §7). Presence verification is now a
team feature (decisions, 2026-11-26).

This file records the full history of the module, so the report can be written without re-deriving anything. Every
number here was measured in a session and states where it came from.

- Short public description: [`ml/face_quality/README.md`](../ml/face_quality/README.md).
- Hand test checklist: `ml/face_quality/TEST.md` (git-ignored by the user).
- Original plan, in Vietnamese: `ml/face_quality/KE_HOACH.md` (git-ignored).

Last updated: 2026-11-27 (scan fixes from live-scan logs).

---

## 1. What the feature is

The **Add person** page no longer takes uploaded photos. It runs a guided face scan in one of two modes:

- **Live scan** (default): the phone or webcam camera streams preview frames to the backend. The backend answers each
  frame with a face box, head pose, quality score and a hint ("left side: turn your head to your left", "too dark"…).
  It keeps the best frames for five pose slots: front, left, right, up and down, 3 photos each.
- **Upload video**: a 15 s video is sampled at 5 fps and goes through the same per-frame pipeline.

Each frame is scored by a **face-quality model trained in this repo**. The score estimates how useful the frame is to
**the team's own recogniser** (`ml/face_recognition` v1), not how good it looks to a person. Each kept photo has also
passed anti-spoofing, and every kept photo is checked against the gallery for a duplicate registration.

Why this counts as innovative (the claims the report makes):

1. The model is *recognition-aware*: its labels come from the team's recogniser, with no hand labelling.
2. It is evaluated with the standard method for face-image quality, **EDC curves**, against two baselines.
3. The threshold is chosen from data.
4. The model is built into a complete enrolment flow (pose guidance, liveness, duplicate check, audit file
   `scan.json`).

## 2. Timeline

| Date | What | Commit |
| --- | --- | --- |
| 2026-11-26 | Plan agreed (`KE_HOACH.md`, decisions D1–D13) | — |
| 2026-11-26 | Notebook 01 run locally: labels built | in `1e11951` |
| 2026-11-26 | Backend scan API, tests, detector landmarks | `d73deac` |
| 2026-11-26 | Frontend `FaceScan.vue` replaces upload on Add person | `46c9a68` |
| 2026-11-26 | Notebooks 02 and 03 run on Colab (T4). Weights, results and figures committed, plus README, `model_versions.json` v1 and the System log entry. App threshold set to 0.65 (user decision) | `1e11951` |
| 2026-11-26 | Retry limit (3 attempts of 10 s, failure log) replaces the 60 s limit. Meter shows why a frame is refused. Hints say "a little less" when the head turns past a slot. `start.ps1` waits for the backend | `86cc5e6` (user's commit) |
| 2026-11-26 | Per-person pose baseline, wider slots, eye-aligned quality crop, detection at preview width, live stills reuse the preview liveness, `same_view` reason | `a546102` |

Colab issues hit on the way: `images.npy` and `face_recognition.pt` were not uploaded to Drive at first. The Kaggle
download with `curl` saved an HTML error page as `archive.zip`; notebook 03 now uses `kagglehub` or a copy on Drive.

## 3. Files

| File | Role |
| --- | --- |
| `ml/face_quality/01_build_labels.ipynb` | Kaggle crops → damage → recogniser embeddings → labels (`data/raw/face_quality/labels/`, git-ignored) |
| `ml/face_quality/02_train_quality.ipynb` | Training (Colab) → `face_quality.pt` |
| `ml/face_quality/03_evaluate.ipynb` | EDC, Spearman, damage response, threshold → `results.json`, `figures/` |
| `ml/face_quality/infer.py` | `build_model`, `score`, `score_batch`, `align_crop`, `threshold`, `info` |
| `ml/face_quality/damage.py` | The 9 synthetic damage types |
| `ml/face_quality/heuristic.py` | Baseline score; also the backend fallback when the weights are missing |
| `backend/app/services/enrol.py` | Sessions, per-frame `analyse()`, slots, hints, calibration, liveness, duplicate check, video, `save()` → `scan.json`, `fail()` |
| `backend/app/api/enrol.py` | `POST /api/enrol/session`, `POST /frame`, `POST /video`, `GET` / `DELETE /session/{id}`, `GET /session/{id}/still/{slot}/{i}`, `POST /session/{id}/fail` |
| `backend/app/api/records.py` | `POST /api/students` accepts an optional `enrol_session` in place of `photos` (additive) |
| `backend/app/pipeline/detector.py` | `detect_faces_landmarks()` (YuNet box + 5 landmarks); `detect_faces()` unchanged |
| `backend/app/services/model_log.py` | `face_quality` appears on the System log page |
| `backend/tests/test_enrol.py` | 15 tests with fake models (session logic only) |
| `frontend/src/components/FaceScan.vue` | Live scan / Upload video tabs, overlay, quality meter with reason, retry counter, review grid |
| `frontend/src/pages/AddPerson.vue`, `frontend/src/api.js` | Form wiring, scan API helpers |
| `start.ps1` | Starts the backend, waits for HTTP, then starts the frontend |

## 4. The model

### Data and labels (notebook 01, run locally)
- Kaggle `classification_data`, the same archive and pin as `ml/face_recognition` (SHA-256 `ec28aa01…6f60`). The
  crops are 64×64 and pre-aligned.
- 800 identities × 10 clean crops, plus 2 damaged copies of each crop, give **24 000 crops**. The split is by
  identity: 640 for training and 160 for validation, so 19 200 / 4 800 crops.
- Damage types (`damage.py`), each at a random level: blur, motion blur, noise, JPEG, downscale, dark, bright,
  occlusion, pose.
- **Label** = cosine similarity between the crop's `face_recognition` v1 embedding and the mean embedding of the
  *other* clean crops of the same person (leave-one-out). It is rescaled by the 1st and 99th percentiles
  (0.358, 0.901) and clipped to [0, 1].
- Sanity checks: clean crops average 0.77 and damaged crops 0.52. For every damage type, the label falls as the level
  rises. Spearman between label and damage level:

| Damage | blur | motion | noise | jpeg | downscale | dark | bright | occlusion | pose |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Spearman | −0.69 | −0.55 | −0.73 | −0.44 | −0.54 | −0.43 | −0.82 | −0.54 | −0.43 |

### Model and training (notebook 02, Colab T4)
- MobileNetV3-Small, ImageNet weights, all layers fine-tuned, 1.07 M parameters, sigmoid regression head.
- Input: 112 px RGB with ImageNet normalisation.
- Training: 12 epochs, batch 128, one-cycle schedule, backbone learning rate 3e-4, head learning rate 1e-3,
  Huber loss (δ 0.1), weight decay 1e-4, horizontal-flip augmentation, seed 30082.
- **Best epoch 2, validation Spearman 0.728** (MAE about 0.12). After that the training loss keeps falling while the
  validation loss rises: the model **overfits early**.
- Validation Spearman within each damage type:

| Type | clean | blur | motion | noise | jpeg | downscale | dark | bright | occlusion | pose |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Spearman | **0.35** | 0.73 | 0.66 | 0.71 | 0.47 | 0.65 | 0.52 | 0.80 | 0.62 | 0.47 |

  The model ranks damaged frames well but **ranks clean frames poorly**.

### Evaluation (notebook 03, Colab, `results.json`)
- 8 805 verification pairs (4 315 genuine) from `verification_pairs_val.txt`, 9 355 images, identities never seen in
  training.
- **EDC**: discard the lowest-quality pairs first and track the false non-match rate (FNMR) at a fixed 1 % false-match
  rate. The pAUC column is the area under the EDC curve from 0 to 30 % discarded, ×100; lower is better.
- Two sets: *clean*, and *camera-like*, where about half the images carry a random damage.

| Score | pAUC clean | pAUC camera-like | Spearman with labels |
| --- | --- | --- | --- |
| **Trained model** | **57.86** | **79.37** | **0.728** |
| Heuristic | 59.14 | 80.80 | 0.247 |
| Feature norm | 59.47 | 81.45 | 0.200 |
| Random discard | ≈ 59.9 | ≈ 82.3 | — |

- FNMR with nothing discarded is 59.6 % on clean pairs and 82.3 % on camera-like pairs. That high starting point is a
  limit of the **recogniser** on 64 px crops, not of the quality model.
- On camera-like pairs, discarding 30 % lowers FNMR to 76.2 % with the trained model, against 78.9 % with the
  heuristic.
- The predicted score falls steadily with the level of every damage type (`figures/damage_response.png`).
- **Threshold from data: 0.78.** Rule: the lowest t at which camera-like pairs with both images ≥ t reach an FNMR of at
  most 1.1 × the clean FNMR. At 0.78 the model accepts 69 % of clean crops but only 4–9 % of blurred, motion-blurred,
  noisy or occluded ones (jpeg 31 %, downscale 29 %, dark 30 %, bright 26 %, pose 19 %). The value is stored in
  `face_quality.pt`.

## 5. The domain gap (Kaggle → webcam)

v1 was trained on 64 px Kaggle crops. On 27 webcam frames of 2 people (`AppliedML/{Minh Thành, Đức Mạnh}/WIN_*.jpg`):
- Its data threshold 0.78 passed only 3 of 27 frames (median 0.67 / 0.75), so the app ran v1 at 0.65 (user).
- Crop framing mattered more than resolution: margin 0.0 / 0.1 / 0.2 / 0.3 around the YuNet box gave medians 0.658 /
  0.712 / 0.724 / 0.750. `infer.align_crop()` reproduces the Kaggle framing (eyes level, eye distance 0.189 of the
  side, 128 px) and is what the scan feeds the model; its effect alone was small (median 0.712 → 0.719).
- Conclusion: framing explains only part of the gap; in-domain data was needed (§10).

## 6. How the scan decides, per frame (current code)

`analyse(s, image, final)` in `services/enrol.py`:

1. **Detect** with YuNet at most 640 px wide (`DETECT_W`). Faces smaller than half the main face are ignored; another
   face → `several_faces`; none → `no_face`.
2. **Pose** from the 5 landmarks (`head_pose`), rough geometry, not solvePnP. **Calibration**: the first 4 frames with
   |yaw| ≤ 25, |pitch| ≤ 30 give a per-person baseline (median); until then `calibrating`.
3. **Live scan only**: preview poses are the median of the last 3 (`POSE_SMOOTH`), and the slots are filled **in
   order** front → left → right → up → down. Only the current target slot accepts stills; a later pose not reached
   yet → `other_pose`. The target's ranges are widened by `TARGET_MARGIN` 3° (`TARGET_MARGIN_UP` 5° for up). Video
   uploads keep any order.
4. **Quality**: the trained model on `align_crop(image, landmarks)` (heuristic at 0.35 without weights). The bar is
   **relative to the person in this session** (`_quality_bar`): median of the first 8 front preview scores minus 0.06,
   capped at the checkpoint threshold (v2: 0.58), floored at 0.45; up gets −0.06 more (`SLOT_QUALITY_OFFSET`). The
   frame's `threshold` field is this bar, so the meter marker moves with it.
5. **Liveness**: anti-spoofing over the last 10 crops; every 3rd preview frame in a live scan (the still reuses it),
   every frame of a video.
6. **Gates in order**: `not_live` → `too_dark` (< 60) → `too_bright` (> 200) → `too_small` (< 110 px on 1080p+,
   < 80 px otherwise) → `between_poses` → `other_pose` → `low_quality` → `same_view` (a better still within 4°, or the
   slot is full of better ones) → `ok`.
7. **Slots** (degrees relative to the baseline, ranges touch): front yaw ±12 / pitch ±10; left yaw 12…55; right
   −55…−12 (pitch ±20 for both); up pitch −45…−10; down 10…45 (yaw ±12). 3 photos each, ≥ 4° apart, 15 in total.
8. **Duplicate check**: every kept still is matched against the registered faces (`face_recognition` crop); the
   warning appears once 2 stills (`DUPLICATE_MIN_VOTES`) match the same student. A new session starts loading the
   registered faces in the background (they stay empty until something loads them).
9. **Page flow**: preview at 640 px every 250 ms; an `ok` preview for a missing slot triggers a full-resolution still
   (`final=true`) that runs the same gates. An attempt fails after 10 s without a new photo; after 3 the scan stops
   and `logs/enrol_failures.jsonl` gets a line.
10. **Display**: top (blue) = the **instruction** with "Step n of 5 · <slot>"; it changes only when a new hint arrives
    twice in a row. Bottom = **"Status: …"** next to the meter (green kept, amber quality passes but another gate
    fails, red quality below the bar).
11. **Logs**: every scored frame → `logs/enrol_frames.jsonl` (target, slot, yaw, pitch, quality, bar, reason, face px,
    YuNet `face_conf`, brightness, kept). `save()` writes `data/photos/<id>/photo_NN.jpg` + `scan.json`.

## 7. Bugs found and fixed (with evidence)

| Symptom | Cause | Fix | Evidence |
| --- | --- | --- | --- |
| Meter green but no photo | Meter showed only quality ≥ threshold | Three-colour meter with the reason | — |
| "turn right" while filling left | No overshoot handling | Slot-named hints, "a little less" | `test_overshoot_says_turn_back_not_other_side` |
| Hard to fill slots | Fixed pitch zero, dead zones | Per-person baseline, touching slots | `test_calibrates_on_the_persons_own_straight_pose` |
| "still rejected" while holding still | Liveness re-run on the still, no face at full res, same-view drop shown as a rejection | Preview liveness, detection at 640 px, `same_view` | 21-frame replay: 9 → 14 of 14 kept |
| Slots filled out of order, status jumping (2026-11-27) | Any missing slot accepted; per-frame landmark jitter | Ordered target slot, pose median of 3, hint debounce | `test_live_scan_follows_the_slot_order` |
| "not sharp enough" on chin up (2026-11-27) | v2 scores up low (its labels are recognition similarity, which drops with pose) | −0.06 for up | Scan 1 medians: front 0.70, left 0.70, right 0.74, down 0.65, **up 0.57** (24 of 42 below 0.58) |
| "not sharp enough" everywhere (2026-11-27) | v2's level moves between sessions: scan 2 front median 0.55, same light, larger face | Session-relative bar | Log replay, scan 2: front 77/130, left 101/110, up 31/35 pass (before 49/130, 40/110, 3/35) |
| No duplicate warning when Đức Mạnh re-registered as TEST (2026-11-27) | Only the first (front) still was checked and it matched Hồng Minh; the gallery could be empty | Vote over all stills, warm the gallery | 15 TEST stills vs the gallery: 8 match Đức Mạnh; front stills match Hồng Minh (0.78–0.80) |

## 8. Decisions

| # | Decision | Why |
| --- | --- | --- |
| D2 | No super-resolution / face restoration for gallery photos | Invents detail, shifts the embedding |
| D3/D8 | Labels from `face_recognition` v1; quality pinned to it | Self-supervised; rerun 01 → 03 and bump if the recogniser changes |
| D4 | MobileNetV3-Small | Small, fast on CPU |
| D5–D7 | Baselines heuristic + feature norm; threshold from data; report honestly even if it loses | Assignment marks honest evaluation |
| D9/D10 | HTTP frames ~4 fps; video at 5 fps, same pipeline | Simple, works over the LAN |
| — | v2 adopted (06 MobileNetV3 B, 0.58) (2026-11-26, user) | §10 |
| — | 3 attempts of 10 s, failures logged (user) | User request |

## 9. Open problems

1. **Chin up is barely seen by the pose estimate**: in a real scan pitch stayed at −2…−10° while the person tilted up
   and swung the head looking for it. Candidates: solvePnP with a generic 3D face, or per-person pitch scaling.
2. **Occlusion is not detected**: a hand over half the face is still kept (quality, liveness and YuNet all pass).
   In progress: `face_conf` is logged; compare a clean and a covered scan, gate on it (`occluded`) if they separate,
   else check identity consistency against the session's kept stills.
3. **v2's score level is unstable between sessions** (handled by the relative bar; cause unknown).
4. **The recogniser confuses Đức Mạnh / Hồng Minh / Thuận Minh**: lead over the runner-up 0.02–0.08 on the TEST stills.
5. Measured on 2 live scans of one person only, never on a phone. No end-to-end proof yet that scan enrolment beats
   uploaded photos (next step below).

## 10. Model versions after v1 (summary; the executed notebooks hold the full outputs)

EDC pAUC = area under FNMR vs share discarded, 0–30 %, ×100; lower is better.

- **04_finetune_team (photos only)**: v1 fine-tuned on 3 members' photos with synthetic damage, 2 held out. Spearman
  0.621 vs v1 0.583, but it memorised the training people (train 0.96, test flat 0.60–0.63) and its threshold rule
  gave 0.81 (12 % of clean crops pass). Not adopted.
- **05_finetune_video (photos + recorded takes)**: 625 video faces named by OpenCV SFace + track vote (99.5 %
  agreement). On all held-out video faces the heuristic won (Spearman 0.57 vs 0.28): failures there are mostly 53 px
  classroom faces, which the scan refuses as `too_small` anyway. Not adopted.
- **06_backbones**: same protocol for 4 backbones, selected on held-out video faces ≥ 80 px (n 114, mostly one person):

| Method | video ≥ 80 px | photos | CPU / crop |
| --- | --- | --- | --- |
| MobileNetV3 B × size term | 31.42 | 44.17 | 8 ms |
| **MobileNetV3 B (= v2)** | **32.21** | 44.17 | 8 ms |
| heuristic | 32.72 | 47.33 | — |
| EfficientNet-B0 B | 33.13 | 45.06 | 20 ms |
| ConvNeXt-Tiny B | 33.66 | 44.16 | 60 ms |
| ResNet-18 face B | 35.85 | 45.19 | 21 ms |
| v1 | 35.95 | 44.18 | 8 ms |

  Bigger backbones fit Kaggle better but transfer worse; in-domain stage B helped every backbone (−1.2 to −4.4).
  v2 = MobileNetV3 B, threshold 0.58 (10th percentile of held-out clean photos). Caveats: 2 test people, and the
  candidates were chosen on that set.

**Next (report's key result)**: enrol each member from photos and from a scan, run recognition on the
attendance-camera takes with each gallery, compare correct / wrong / Unknown, and report it honestly either way.

## 11. Pointers for the report

- Method: §4, §6. Results: `ml/face_quality/results*.json`, `figures/`, the executed notebooks.
- Honest limits: §5, §9, D8; a video upload cannot prove presence (the live scan is the default for that reason).
- Engineering story: §7 (each fix backed by a measurement or a replay).
