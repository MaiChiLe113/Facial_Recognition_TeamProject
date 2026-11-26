# Face quality + AI enrolment scan: full record

Owner: Đức Mạnh. This is his graded **individual innovative feature** (assignment §7). Presence verification is now a
team feature (decisions, 2026-11-26).

This file records the full history of the module, so the report can be written without re-deriving anything. Every
number here was measured in a session and states where it came from.

- Short public description: [`ml/face_quality/README.md`](../ml/face_quality/README.md).
- Hand test checklist: `ml/face_quality/TEST.md` (git-ignored by the user).
- Original plan, in Vietnamese: `ml/face_quality/KE_HOACH.md` (git-ignored).

Last updated: 2026-11-26 (v2 adopted).

---

## 1. What the feature is

The **Add person** page no longer takes uploaded photos. It runs a guided face scan in one of two modes:

- **Live scan** (default): the phone or webcam camera streams preview frames to the backend. The backend answers each
  frame with a face box, head pose, quality score and a hint ("left side: turn your head to your left", "too dark"…).
  It keeps the best frames for five pose slots: front, left, right, up and down, 3 photos each.
- **Upload video**: a 15 s video is sampled at 5 fps and goes through the same per-frame pipeline.

Each frame is scored by a **face-quality model trained in this repo**. The score estimates how useful the frame is to
**the team's own recogniser** (`ml/face_recognition` v1), not how good it looks to a person. Each kept photo has also
passed anti-spoofing, and the first kept photo is checked against the gallery for a duplicate registration.

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
| `backend/tests/test_enrol.py` | 13 tests with fake models (session logic only) |
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

## 5. The domain gap (Kaggle → webcam) and what was tried

Test set: 27 webcam frames with a detected face, from `AppliedML/{Minh Thành, Đức Mạnh}/WIN_*.jpg`. They are 1280×720
and show only 2 people.

1. **Threshold 0.78 refuses almost every webcam frame.** Only 3 of 27 frames scored ≥ 0.78; the median was 0.67 for
   Minh Thành and 0.75 for Đức Mạnh. **Decision (user): the app uses 0.65** (`QUALITY_THRESHOLD_WEBCAM`); the
   checkpoint keeps 0.78. With 0.65, 15 of the 16 frontal frames passed. This is a hand calibration on two people.
2. **The crop framing matters more than the resolution.** Scores of the same 27 frames:

| Margin around the YuNet box | Median | ≥ 0.65 | ≥ 0.78 |
| --- | --- | --- | --- |
| 0.0 | 0.658 | 52 % | 4 % |
| 0.1 (the old crop) | 0.712 | 78 % | 11 % |
| 0.2 | 0.724 | 89 % | 22 % |
| 0.3 | 0.750 | 93 % | 26 % |

   Shrinking crops to 64 px like Kaggle changed almost nothing (±0.01).
3. **Kaggle framing measured.** YuNet on 400 clean training crops, upscaled ×4, gives these medians: eye distance 0.189
   of the side, eye midpoint at (0.501, 0.428), YuNet box 42 % of the side. The training crops are loose, while the
   old app crop had the box at about 83 % of the side. `infer.align_crop()` reproduces the training framing (eyes
   level, 128 px), and the scan now feeds it to the model.
4. **Effect of `align_crop`: small.**
   - Webcam frames: median 0.712 → 0.719; ≥ 0.78 went from 11 % to 26 %; ≥ 0.65 stayed at 78 %.
   - Check on 454 Kaggle validation crops, upscaled ×4 then re-aligned: Spearman with labels dropped from 0.536 to
     0.457, and the correlation with the scores of the original crops was 0.76. Upscaling artefacts may explain part of
     the drop, but this is no proof that the aligned crop is better.
   - Conclusion: framing explains only part of the gap. The rest needs in-domain training data (plan §9).

## 6. How the scan decides, per frame (current code)

`analyse(s, image, final)` in `services/enrol.py`:

1. **Detect** with YuNet on a copy at most 640 px wide (`DETECT_W`); boxes and landmarks are scaled back. Faces
   smaller than half the main face are ignored (people in the background). Any other face → `several_faces`.
   No face → `no_face`.
2. **Pose** from the 5 landmarks (`head_pose`): yaw from the nose offset to the eye midpoint, pitch from the nose height
   between the eye line and the mouth line. This is a rough geometric estimate, not solvePnP.
3. **Calibration**: the first 4 frames with |yaw| ≤ 25 and |pitch| ≤ 30 give a per-person baseline (median). Until it
   exists the reason is `calibrating`; afterwards yaw and pitch are relative to the baseline.
4. **Quality**: the trained model on `align_crop(image, landmarks)`, or the heuristic at 0.35 when the weights are
   missing.
5. **Liveness** (anti-spoofing over the last 10 crops). In a live scan it is computed every 3rd preview frame; a live
   full-resolution still reuses the preview result. In a video it is computed on every sampled frame.
6. **Gates in order**: `not_live` → `too_dark` (grey mean < 60) → `too_bright` (> 200) → `too_small` (face < 110 px on
   1080p+, < 80 px otherwise) → `between_poses` (no slot) → `low_quality` (< 0.65) → `same_view` (a better still within
   4° of this one in the slot, or the slot is full of better ones) → `ok`.
7. **Slots**, in degrees relative to the baseline; the ranges touch, so there is no dead zone:

| Slot | yaw | pitch |
| --- | --- | --- |
| front | −12…12 | −10…10 |
| left | 12…55 | −20…20 |
| right | −55…−12 | −20…20 |
| up | −12…12 | −45…−10 |
| down | −12…12 | 10…45 |

   Each slot keeps 3 photos, each at least 4° apart; 15 photos in total.
8. **Live flow in the page**: preview at 640 px every 250 ms. When a preview frame is `ok` for a missing slot, the page
   grabs the full-resolution frame and sends it with `final=true`, and the backend runs the same gates on it before
   keeping it.
9. **Attempts**: an attempt fails after 10 s without a new kept photo. After 3 failed attempts the scan stops and
   `POST /session/{id}/fail` appends a line to `logs/enrol_failures.jsonl` (reason, attempts, reason counts, kept,
   missing). The video upload is still limited to 60 s and 300 MB.
10. **Hints** name the slot being filled and say "a little less, turn back slightly" when the head turns past it, so
    overshooting left is not read as "now do right".
11. **Meter**: green = this frame is being kept; amber = quality passes but another gate fails; red = quality below
    the threshold. A short reason label is shown next to it.
12. **`save()`** writes `data/photos/<student id>/photo_NN.jpg` and `scan.json`: source, time, quality model and
    threshold, per-photo slot / yaw / pitch / quality / face size / brightness / liveness / glasses / video time,
    missing slots, duplicate, frames analysed, model versions.

## 7. Bugs found and fixed (with evidence)

| Symptom | Cause | Fix | Evidence |
| --- | --- | --- | --- |
| Meter green but no photo taken | The meter showed only quality ≥ threshold | Three-colour meter with the reason | — |
| "turn your head to your right" while filling *left* | The hint compared yaw to the range with no idea of overshoot | Slot-named hints, "a little less" past the slot | `test_overshoot_says_turn_back_not_other_side` |
| Hard to fill slots | Fixed zero for pitch (0.55 constant), dead zones between slots | Per-person baseline, wider touching slots | `test_calibrates_on_the_persons_own_straight_pose` |
| `/api/enrol/video` 500 `KeyError: 'done'` | The calibrating return lacked keys | Added `done` and `duplicate` | smoke test |
| Many "still rejected (moved?)" while holding still | (a) re-running liveness on the full-res still turned 8 of 21 webcam stills `not_live`; (b) YuNet found no face on 4 of 21 full-res stills; (c) a still in the same view was dropped but reported as a rejection | Liveness from the preview only; detection at 640 px; `same_view` reason in the preview | Replay of 21 webcam frames: before, 9 of 21 kept; after, 14 of 14 kept |
| Vite `ECONNREFUSED` on startup | The frontend started before the backend | `start.ps1` waits for an HTTP answer | — |

Smoke test (video built from Đức Mạnh's webcam photos, each held 15 frames): liveness 0.9986, front 3 photos
(quality 0.81–0.83), side photos 0.72–0.78. The up and down slots stay empty because the source photos have no such
poses.

## 8. Decisions

| # | Decision | Why |
| --- | --- | --- |
| D2 | No super-resolution or face restoration for gallery photos | It invents detail and moves the embedding away from the real person |
| D3 | Labels come from `face_recognition` v1 | Self-supervised, and tied to the recogniser the app uses |
| D4 | MobileNetV3-Small, fully fine-tuned | Small and fast on CPU, and it is our own training |
| D5 | Baselines: heuristic and feature norm | Shows the model adds value |
| D6/D7 | Threshold from data; ship even if the model loses, and report honestly | Assignment marks honest evaluation |
| D8 | Pinned to `face_recognition` v1 | If the recogniser changes, rerun 01 → 02 → 03 and bump `face_quality` |
| D9/D10 | HTTP frames about 4 fps; video sampled at 5 fps through the same pipeline | Simple, and works over the LAN |
| D11 | API changes only add fields and endpoints | Repo rule |
| — | App threshold 0.65, not 0.78 (2026-11-26, user) | 0.78 refused almost every webcam frame |
| — | 3 attempts of 10 s instead of a 60 s limit, failures logged (user) | User request |

## 9. Current state and open problems

**State:** everything above is committed on `auto-add-face` (`a546102`) and nothing is pushed. 76 backend tests pass
and `npm run build` passes.

**User feedback after the latest fixes: "better, but still not good".** Known or suspected weak points, none of them
measured on real scans yet:

1. **No real-scan data.** Every number in §5 and §7 comes from 27 still webcam photos of 2 people, replayed. There are
   no measurements of real live scans: completion rate, time per slot, which gate refuses most frames, and none from
   a phone.
2. **Pose estimate** is a landmark heuristic. Up and down are the least reliable (pitch from the nose position).
3. **Quality domain gap**: the model is trained on 64 px Kaggle crops; the threshold 0.65 is a guess on 2 people; the
   model ranks clean frames poorly (Spearman 0.35).
4. **Strict capture rule**: 15 photos across 5 slots, each ≥ 4° apart.
5. **Liveness on static frames**: in the replay test, anti-spoofing called some real-person webcam frames not live
   when the same frame was repeated (expected for a static image, but unchecked on real live scans).
6. **No end-to-end proof yet** that scan enrolment beats uploaded photos for recognition, which is the claim the report
   most needs.

## 10. Improvement plan: measure first, then change one thing at a time

Rule: every change states a hypothesis, the metric it should move and a before/after number on the same recorded
data. It is kept only if the number improves. No more patches based on one observation.

### Phase 0: instrument (no behaviour change)
- Log every analysed frame per session to `logs/enrol_frames.jsonl`: time, source, frame size, reason, quality, raw
  and calibrated yaw / pitch, slot, face px, brightness, liveness score, kept, and backend latency.
- Optional per session: save the preview frames to `data/raw/enrol_sessions/<session>/` (git-ignored) so the same scan
  can be **replayed offline** through `analyse()` after any change.
- Add a replay script (`ml/face_quality/replay_scans.py`) that prints the metrics below for a folder of sessions.

### Phase 1: collect a baseline
- At least 10 scans: the 5 team members, laptop webcam and phone, normal and poor light; plus 2–3 attack attempts
  (printed photo, phone screen).
- **Metrics**: completion rate; time to complete; time per slot; distribution of refusal reasons per slot; still
  acceptance rate (preview `ok` → still kept); number of retries; false accepts for the attacks.

### Phase 2: fix the dominant gate, guided by the Phase 1 data
Expected candidates, to be checked against the data:

| If the data shows | Change | Check |
| --- | --- | --- |
| `between_poses` dominates up / down | Pose by solvePnP on the 5 landmarks with a generic 3D face, or per-person scaling of pitch from the calibration frames | Time per slot, on replays |
| `low_quality` dominates on good-looking frames | Retrain (below), or set the threshold from in-domain labels | Spearman on the in-domain set, EDC |
| `same_view` or slot-full time dominates | Fewer photos per slot (2), or accept when front plus 3 of 4 sides are done | Completion time, and the recognition check in Phase 3 |
| `not_live` on real faces | Measure the anti-spoofing false-reject rate on enrolment crops; tune its window or threshold for enrolment | False rejects vs attack accepts |

### Phase 3: retrain the quality model on in-domain data (Colab)

**Status (2026-11-26): notebook written and smoke-tested on a tiny CPU subset, not yet run on Colab.**
- `ml/face_quality/04_finetune_team.ipynb` is uploaded to Drive (`face_quality_colab/repo/ml/face_quality/`), together
  with the updated `infer.py` (it adds `align_matrix`).
- Team photos: `AppliedML/<person>/` (JPEG, PNG, HEIC, rotated by EXIF; `fake_*` spoof images excluded), 5 people.
  Hồng Minh and Mai Chi are held out for testing; training uses Minh Thành, Thuận Minh and Đức Mạnh.
- Each photo is turned into an unrotated 384 px view with the face box 160 px tall, and gets 12 random damages. The
  quality input (`align_crop`) and the recogniser input (`crop_face` rule) are both cut from that same view. Check: the
  notebook's recogniser crop matched the app's crop at cosine 0.95–0.998 on 8 photos; a first attempt that cut from
  the rotated crop gave only 0.79–0.90 and was replaced.
- Fine-tuning starts from v1: 8 epochs × 150 steps, each batch half team / half Kaggle, learning rate 1e-4 / 3e-4,
  augmentation of framing (scale, shift, rotation), flip and mild colour jitter. The last epoch is kept; nothing is
  selected on the test people.
- Output: `face_quality_v2.pt` (v1 untouched), `results_v2.json`, `figures/v2_{edc_team,threshold,training}.png`.
  The threshold is chosen on the held-out team crops with v1's rule, and stored with `threshold_domain: "webcam"`. The
  backend then uses the checkpoint's threshold instead of `QUALITY_THRESHOLD_WEBCAM`.
- To adopt v2: copy it over `face_quality.pt`, bump `face_quality` to v2 in `ml/model_versions.json`, and update
  README / this file with the results.
- Caveat for the report: only 2 test people (about 20 photos), so the in-domain numbers are indicative, not
  conclusive.

**Result of the Colab run (2026-11-26, `results_v2.json`, `figures/v2_*.png`, executed notebook in the repo):**
- Data: 95 photos with a face (13 had no face found at 640 px), 1 235 crops. Train: Minh Thành 27, Thuận Minh 28,
  Đức Mạnh 14 photos (897 crops). Test: Hồng Minh 13, Mai Chi 13 photos (338 crops, 26 clean).
- Labels on team crops: clean mean 0.768, damaged 0.585. Clean cosine median 0.783; 3 of 26 clean test photos are
  already below the recogniser threshold (0.692). The label falls with the damage level for every type, but less
  steeply than on Kaggle (downscale −0.18, pose −0.26, against −0.54 and −0.43 on Kaggle).

| On the 2 held-out people | v1 | v2 | heuristic |
| --- | --- | --- | --- |
| Spearman with labels (338 crops) | 0.583 | **0.621** | 0.241 |
| Spearman, clean crops only (26) | −0.03 | 0.07 | −0.01 |
| EDC pAUC 0–30 % (recognition failures among kept, %) | 44.18 | **44.00** | 47.33 |
| Kaggle val Spearman (2 000 crops) | 0.723 | 0.725 | — |

- Training curve: team-train Spearman went from 0.84 to 0.96 while team-test stayed flat at 0.60–0.63. **The model
  memorises the 3 training people.** Kaggle stayed flat, so there was **no forgetting**.
- v2 beats v1 slightly on Spearman (+0.04). The EDC curves overlap (v1 is lower at 25–30 % discarded), so the
  difference is **within noise** for 26 clean photos of 2 people. Both models beat the heuristic clearly.
- **The chosen threshold, 0.81, is unusable.** It accepts only 12 % of clean held-out crops. The rule (failure rate
  among accepted ≤ 1.1 × clean failure rate) degenerates on a small set where clean and damaged scores overlap: it
  can only be met by a cut that leaves 3 clean crops. Do not ship it.
- **Decision pending (user): v2 not adopted yet.** The app still runs v1 at 0.65.

### Phase 3b: v3, with real camera faces from the recorded takes (`05_finetune_video.ipynb`)

**Status (2026-11-26): written, smoke-tested on a tiny CPU subset (take 3 at 0.5 fps), uploaded to Drive, not yet run
on Colab.** Notebook 04 and v2 are kept unchanged as the record of the photos-only attempt.
- **Why:** v2 memorised its 3 training people because there was too little in-domain data.
- **New data:** faces from the 8 recorded takes × 3 cameras (`AppliedML/video data/`), sampled at 3 fps; YuNet on
  the full 1280×720 frame, faces ≥ 32 px. Crops are cut as the app cuts a frame (`align_crop` / `crop_face`). At
  most 40 faces are kept per track. No synthetic damage: the blur, distance and light are real.
- **Naming without bias:** the labels come from the team recogniser, so faces are named with an independent model,
  OpenCV **SFace**, against the enrolment photos. A face is "sure" at cosine ≥ 0.40 with a margin of 0.06; a person
  track (`video_tracks.json`, built by `build_video_tracks.py` from `data/tracks/`) is named when it has ≥ 3 sure
  votes that agree ≥ 80 %. Track voting brings in faces SFace could not name alone (the hard cases). In the smoke
  test, SFace's own sure name matched the track name on 93 % of faces.
- **Labels:** cosine of the team recogniser between the video crop and the mean of that person's enrolment photos
  (what the app matches against), rescaled with v1's percentiles.
- **Kept from 04:** split by person (test: Hồng Minh, Mai Chi), fine-tune from v1, half team / half Kaggle per batch,
  the same augmentation, last epoch kept.
- **New threshold rule:** the 10th percentile of v3's score on the held-out clean enrolment photos (90 % of good
  photos pass), then checked on the held-out video faces (share accepted, failure rate among accepted vs refused).
  04's rule degenerated; it is still reported (`v1_rule_value`).
- **Evaluation views:** real video faces (the main result), photos with synthetic damage, and all together, each
  for v1, v2, v3 and the heuristic.
- **Outputs:** `face_quality_v3.pt`, `results_v3.json`, `figures/v3_{edc_team,threshold,training}.png`. No face
  images are displayed or saved.
- Smoke-test sign of a known problem: attendance-camera faces of about 190 px scored a mean label of only 0.49. The
  team recogniser is weak on camera frames (status.md, "Recognition on doorway frames is weak"), so many real
  crops get low labels. That is correct for the label rule, but it bounds what the quality model can learn.

**Result of the Colab run (2026-11-26, `results_v3.json`, `figures/v3_*.png`, executed notebook in the repo).**

Video data:
- 1 498 faces detected; SFace was sure on 453. 707 faces were named, 698 of them by track vote, and 298 of those
  SFace could not name alone. 625 faces were kept after the cap.
- **Naming check:** inside voted tracks, SFace's own sure name matched the track name on **99.5 %** of 400 faces.
  25 of 43 tracks with any sure vote were named.
- Faces per person: Hồng Minh 221 (attendance 88, cam_1 20, cam_2 113), Mai Chi 16 (attendance only), Thuận Minh
  191, Đức Mạnh 197, Minh Thành 0 (not in the takes).
- Per camera:

| Camera | Faces | Median face size | Mean label | Recognised (cosine ≥ 0.692) |
| --- | --- | --- | --- | --- |
| attendance_cam | 197 | 208 px | 0.610 | 51 % |
| cam_1 | 50 | 54 px | 0.480 | 12 % |
| cam_2 | 378 | 53 px | 0.488 | 12 % |

- Split: training uses 897 photo crops + 388 video faces; the test uses 338 photo crops + 237 video faces. 221 of the
  237 test video faces are Hồng Minh, so the video test is in effect **one person**.

Results on the held-out people:

| View | Metric | v1 | v2 (photos) | v3 (photos + video) | heuristic |
| --- | --- | --- | --- | --- | --- |
| Video, real (237) | Spearman | 0.336 | 0.434 | 0.283 | **0.570** |
| Video, real (237) | EDC pAUC | 66.37 | 65.48 | 65.79 | **63.05** |
| Photos, synthetic damage (338) | Spearman | 0.583 | 0.621 | **0.625** | 0.241 |
| Photos, synthetic damage (338) | EDC pAUC | 44.18 | **44.00** | 44.12 | 47.33 |
| All (575) | Spearman | 0.352 | 0.448 | **0.521** | 0.390 |
| All (575) | EDC pAUC | **52.81** | 52.89 | 52.86 | 53.24 |
| Kaggle val (2 000) | Spearman | 0.723 | 0.725 | 0.725 | — |

Training curve: team-train Spearman rose from 0.77 to 0.94. The held-out *video* Spearman was best at epoch 1 (0.44),
then fell to 0.21–0.28. Kaggle stayed flat.

Threshold (new rule): **0.59**.
- It accepts 88 % of held-out clean photos and 58 % of held-out video faces (attendance 71 %, cam_1 25 %,
  cam_2 51 %).
- Recognition failures are 57.7 % among the accepted video faces against 79 % among the refused ones (66.7 % overall).
- v1's rule would give 0.79.

**Analysis**
1. **Adding video did not help on real frames; it made the learned ranking worse there** (v3 0.283 against v2 0.434).
   The held-out video curve peaks at epoch 1 and then falls while the training people keep improving. The model
   learns the training people's cameras and scenes, not quality.
2. **On real video the hand-made heuristic wins** (Spearman 0.57, pAUC 63.05). Real recognition failure is driven
   mostly by **absolute face size**: classroom and corridor faces are about 53 px and only 12 % are recognised. The
   heuristic has an explicit face-size term. The learned model only sees the aligned crop resized to 112 px, so the
   absolute resolution is lost (it can only infer it from blur).
3. **The video test does not match how the app is used.** The enrolment scan already refuses faces smaller than 80 or
   110 px (`too_small`), so 54 px classroom faces never reach the quality model in the app. The relevant real-frame
   test is the attendance camera alone (208 px). Per-camera Spearman and EDC were not computed; that is the next check
   (§10, Phase 3c).
4. On synthetic damage and Kaggle, v1, v2 and v3 are equal within noise. All learned models beat the heuristic there.
5. **Naming by SFace plus track vote works** (99.5 % agreement). That part is reusable for any future in-domain set.

**Decision pending (user): v3 not adopted.** The app still runs v1 at 0.65.

### Phase 3c (proposed, not done): evaluate on the app's operating range first
- Add an evaluation cell (no training) that restricts the held-out video to faces ≥ 80 px, which in practice means
  attendance_cam, and compares v1, v2, v3, the heuristic and a **fusion** `model score × size term` from the
  heuristic. If the fusion wins, ship it: no retraining needed.
- If the learned models still lose on that range, keep v1 and report: synthetic damage and Kaggle labels teach what
  the model does well; real camera failures are mainly resolution, which the scan already gates with `too_small`.

### Phase 3d: backbone comparison (`06_backbones.ipynb`)

**Status (2026-11-26): written, smoke-tested on a tiny CPU subset, uploaded to Drive with the updated `infer.py`, not
yet run on Colab.**
- **Why:** the user asked for a stronger backbone than MobileNetV3. The evidence (early overfitting; the heuristic
  winning on real frames through face size) suggests capacity is not the limit, so this is a fair test, not a swap.
- **`infer.py`** now has `ARCHITECTURES` (`mobilenet_v3_small`, `resnet18`, `efficientnet_b0`, `convnext_tiny`),
  `build_model(arch=...)`, `head_of(net)` and `arch_of(payload)`. The architecture comes from the file's
  `architecture` field (`<arch>_quality`). v1 still loads with `strict=True` and gives the same scores.
- **Candidates:** MobileNetV3-Small (ImageNet), **ResNet-18 initialised from the team recogniser's backbone** (already
  trained on faces), EfficientNet-B0 and ConvNeXt-Tiny (ImageNet).
- **Same protocol for all:** stage A on Kaggle only (10 epochs, best epoch on Kaggle validation), then stage B on team
  photos + video faces mixed half and half with Kaggle (8 × 150 steps). Same data as 05, same augmentation, same seed.
- **Views:** `video_app`, the held-out video faces ≥ 80 px, is the primary one: it is the range the scan scores,
  since smaller faces are `too_small`. Also `video_all`, `photos` and Kaggle validation. Methods: each stage-A and
  stage-B model, the v1 file, the heuristic, `size term only`, and `model × size term` (fusion). CPU latency per crop
  is measured too.
- **Selection rule, fixed before the run:** the best `video_app` pAUC among the stage-B models. It replaces
  MobileNetV3 only if it beats it by more than 0.5 pAUC there and is not worse on `photos`.
- **Outputs:** `results_backbones.json`, `figures/backbones_edc.png`, and `face_quality_<winner>.pt` with a
  usability threshold.

**Result of the Colab run (2026-11-26, `results_backbones.json`, `figures/backbones_edc.png`, executed notebook in
the repo).** Held-out set: video faces ≥ 80 px, n = 114, failure rate with nothing discarded 35.1 %. Also all video
faces (n 237) and photos (n 338). EDC pAUC, lower is better.

| Method | video ≥ 80 px | Spearman there | all video | photos | Kaggle val Spearman | CPU / crop |
| --- | --- | --- | --- | --- | --- | --- |
| **MobileNetV3 B × size** | **31.42** | 0.351 | 61.51 | 44.17 | 0.728 | 8 ms |
| EfficientNet-B0 B × size | 32.18 | 0.311 | 61.37 | 45.06 | 0.722 | 20 ms |
| **MobileNetV3 B** | **32.21** | 0.325 | 67.06 | 44.17 | 0.728 | 8 ms |
| ConvNeXt-Tiny B × size | 32.36 | 0.363 | 61.45 | 44.16 | 0.732 | 60 ms |
| heuristic | 32.72 | 0.327 | 63.05 | 47.33 | — | — |
| EfficientNet-B0 B | 33.13 | 0.230 | 66.13 | 45.06 | 0.722 | 20 ms |
| ConvNeXt-Tiny B | 33.66 | 0.333 | 67.41 | 44.16 | 0.732 | 60 ms |
| ResNet-18 face B | 35.85 | 0.125 | 65.65 | 45.19 | 0.767 | 21 ms |
| v1 file (MobileNetV3) | 35.95 | 0.077 | 66.37 | 44.18 | 0.723 | 8 ms |

Stage A (Kaggle only) on video ≥ 80 px: MobileNetV3 36.57, EfficientNet-B0 35.29, ConvNeXt-Tiny 36.23, ResNet-18
face 37.07. Best stage-A epoch on Kaggle validation: 3, 7, 2 and 2 for MobileNetV3, ResNet-18 face, EfficientNet-B0
and ConvNeXt-Tiny, with Kaggle validation Spearman 0.730, 0.772, 0.732 and 0.757. Team-train Spearman after stage B:
0.94 (MobileNetV3), 0.98 (ResNet-18 face), 0.97 (EfficientNet-B0), 0.99 (ConvNeXt-Tiny).

**Analysis**
1. **Bigger backbones fit Kaggle better but transfer worse.** ResNet-18 face reaches the best Kaggle validation
   score (0.772) and the worst real-frame score among stage-B models (35.85). The larger models memorise the
   training people more (team-train 0.97–0.99). On the in-domain question, **capacity is not the bottleneck**; the
   amount and diversity of in-domain people is.
2. **In-domain fine-tuning (stage B) helps on the app's operating range for every backbone** (stage A → B:
   MobileNetV3 −4.4, EfficientNet-B0 −2.2, ConvNeXt-Tiny −2.6, ResNet-18 face −1.2 pAUC). Because the effect is
   consistent across the 4 backbones, it is more convincing than any single number. This qualifies the v3 conclusion,
   which was drawn on *all* video faces, mostly 53 px classroom faces that the scan never scores.
3. **MobileNetV3 stage B beats the v1 file by 3.7 pAUC on faces ≥ 80 px (32.21 vs 35.95) and ties on photos.** It
   is also slightly better than the heuristic (32.72), and it is the fastest model (8 ms).
4. **Fusion with the size term** gives the best overall method (31.42), and on all video faces it beats the
   heuristic (61.5 vs 63.05). In the app it changes little: the scan only scores faces ≥ 80/110 px, where the size
   term is close to 1 (it saturates at 112 px).
5. The selection rule picked MobileNetV3 B, so no bigger backbone replaces it. Saved as
   `face_quality_mobilenet_v3_small.pt`, threshold 0.58 (10th percentile on held-out clean photos). A local copy is
   at `data/raw/face_quality/candidates/` (git-ignored).
6. **Sanity check on the webcam frames** (35 AppliedML `WIN_*` frames of Minh Thành and Đức Mạnh; *training* people
   for this model, so this is not a test): v1 median 0.725, 17 % ≥ its 0.78; the new model median 0.815, 97 % ≥ its
   0.58 and 91 % ≥ 0.65.

**Caveats for the report**
- The test is 2 people, and 98 of the 114 faces ≥ 80 px come from video of mostly one of them (Hồng Minh).
- The candidates were also *chosen* on this test set. The rule favoured the baseline, which won anyway, so the
  optimism is small but not zero.
- The A → B gain is consistent but measured on one small set.

**Decision (user, 2026-11-26): adopted.** The 06 MobileNetV3 B model is now `ml/face_quality/face_quality.pt`, version
v2 in `ml/model_versions.json`, threshold 0.58 from the checkpoint. v1 stays in git history. Checks after the swap:
all backend tests pass; the video smoke test (Đức Mạnh's webcam photos) kept photos in 4 of 5 slots, including
*down* for the first time.
- **Training data**: Kaggle data plus crops from the recorded takes (`AppliedML/video data/`) and the Phase 1 scans.
  Labels use the same rule (leave-one-out cosine with the `face_recognition` gallery of that person). Synthetic damage
  is applied to them too.
- **Augmentation**: random crop scale and offset around the aligned crop, so the score no longer depends on framing;
  colour jitter.
- **Against the early overfit**: lower learning rate or freeze the early blocks, and use more identities (the archive
  has more than the 800 used).
- **Evaluation**: EDC on Kaggle as before, plus Spearman and EDC on a held-out **in-domain** set (team members unseen in
  training). The threshold is chosen on in-domain data with the same rule.

### Phase 4: end-to-end check (the report's key result)
- Enrol each team member twice, once from uploaded photos and once from a scan.
- Run recognition on the recorded takes (attendance camera) with each gallery, and compare correct / wrong /
  `Unknown`, as `ml/face_recognition` README does for its 68 annotated crops.
- If the scan gallery is not better, report that honestly (D7).

### Order and cost
Phases 0–1 take about 1–2 h including the scans. Phase 2 depends on the data. Phase 3 takes about 1 h of work plus
about 10 min of GPU. Phase 4 takes about 1 h. **Do phases 0, 1 and 4 before any further tuning**: they give the report
its evidence even if nothing else changes.

## 11. Pointers for the report

- Method: §4 (labels, model, training), §6 (scan pipeline).
- Results: `ml/face_quality/results.json` and `figures/edc.png`, `figures/damage_response.png`,
  `figures/threshold.png`; the executed notebooks hold the full outputs.
- Honest limits: §5 (domain gap and hand threshold), §9 (no real-scan data yet, early overfit, weak ranking of clean
  frames), D8 (tied to the recogniser version), video uploads cannot prove the person is present (a real video of
  someone else passes anti-spoofing; the live scan is the default for that reason).
- Engineering story: §7 (each bug found by replaying real frames, with before/after counts).
