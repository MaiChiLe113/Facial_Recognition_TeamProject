# Face recognition — Owner: Thuận Minh

- [x] Download and audit the Kaggle dataset (in the notebooks)
- [x] `01_train_classification.ipynb` — ResNet-18 → 512-d → softmax, cross-entropy (128×128 input selected, epoch 18)
- [x] `02_train_triplet.ipynb` — same backbone, triplet loss, semi-hard mining selected (epoch 19 of 20)
- [x] `03_evaluate_verification.ipynb` — ROC/AUC on the verification pairs, cosine vs Euclidean, threshold
- [x] Inference code: `infer.py` (`embed()`, `identify()`), loaded by the backend and the Features demo page
- [x] Demo weights: `face_recognition.pt`, stored in Git alongside `infer.py`
- [x] Replay the model on team enrolment photos and existing attendance-camera faces
- [ ] Check performance on a new recording with registered and unregistered people

The original Kaggle evaluation in `03_evaluate_verification.ipynb` selected **triplet + cosine** at a
cosine threshold ≥ 0.5254 (Euclidean ≤ 0.9743). On 3,314 independent holdout pairs, the original
`selected_model.pt` scored AUC 0.954, with 54.1 % true-match acceptance and a 2.0 % false-match rate.

The Features demo page (`backend/app/services/features_demo.py`) also uses the YuNet file below to find faces; without it, it falls back to OpenCV's Haar cascade and loads fewer enrolment photos.

## Demo weights

The checked-in `face_recognition.pt` contains the camera-fine-tuned triplet model. Its matching policy
averages and normalizes each student's
enrolment embeddings. A match requires a cosine similarity of at least 0.692213 (rounded) and a
lead of more than 0.025 over the runner-up.

Pull the repo, restart the backend and reset the Features page's face threshold slider to use the model
default. The gallery is recomputed for the new weights. Set `HAWKEYE_DRIVE_ROOT` to the folder containing
`AppliedML/` if it is outside the configured Drive location. `HAWKEYE_FACE_RECOGNITION_WEIGHTS` can point
to a different checkpoint for comparison.

[Notebook 03](03_evaluate_verification.ipynb) records calibration on take 1 and comparison on take 3.
On the same 68 annotated camera crops, the camera profile gave 21 correct, one wrong, and 46 `Unknown`.
The earlier camera candidate gave 16 correct, one wrong, and 51 `Unknown`. Both accepted 3/68 simulated
unregistered queries with the true identity removed from the gallery. The regular model gave 34 correct,
33 wrong, and one `Unknown`. Both clips were previously inspected. A new clip with real unregistered
people is needed to assess performance for the demo.

## Offline track naming: `name_tracks.py`

The offline script names people with OpenCV's pre-trained **YuNet** (face
detection) + **SFace** (128-d embedding, cosine similarity, threshold 0.363 as recommended by OpenCV).
Weights go in `ml/face_recognition/models/` (git-ignored), from `github.com/opencv/opencv_zoo`
(~0.2 MB and ~37 MB):

```bash
mkdir -p ml/face_recognition/models
curl -L -o ml/face_recognition/models/face_detection_yunet_2023mar.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
curl -L -o ml/face_recognition/models/face_recognition_sface_2021dec.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
ml/.venv/bin/python ml/face_recognition/name_tracks.py --take all
```

The Drive folder is found from `HAWKEYE_VIDEO_ROOT` in `backend/.env` (two levels up from `video data/`).

- **Enrolment:** every student in the backend's database (`data/hawkeye.sqlite3`, read-only; start the backend once to
  create it) with photos: the files in `photo_folder` and the `student_card` image (`AppliedML/...` paths are relative to
  the Drive folder that holds `AppliedML/`, `data/photos/...` are Add person uploads; HEIC is converted
  into `data/raw/enrol/` with macOS `sips`, or with `pillow-heif` on Windows/Linux:
  `pip install pillow pillow-heif`). A photo with no face found is retried at 960, 640, 480 and 320 px:
  YuNet misses faces that fill a phone close-up. `--db <file>` reads another database.
- **Matching:** each face crop votes only for the student it matches best (with several students
  enrolled, one crop used to count for everyone above the threshold). Each `attendance_cam` track is named
  when at least 3 face crops inside its box match one student. `name_from` = time of the 3rd match, so the UI shows `ID n · Unknown` until check-in and
  `ID n · Mai Chi` after it.
- **All five members enrolled (2026-11-21, full Drive folders, photos + card):** Mai Chi 16 faces / 16
  files, Đức Mạnh 15/15, Thuận Minh 24/24 (incl. his card `TMinh.jpg`), Hồng Minh 9/12 (no face in 3 HEIC
  photos), Minh Thành 24/28 (no face in 4 webcam photos). For this run Minh Thành
  was enrolled from a separate roster file; he is now in the database (Do Minh Thanh), so the default run enrols him too.
  He is not in any of the recorded takes, and he was correctly not named on any track (at most 1 face
  crop per track matched him), so his enrolment caused no false names.
- **Result, takes 1–8 (2026-11-21, run with all five enrolled):**

  | Take | attendance_cam | cam_1 / cam_2 (door handoff) |
  | --- | --- | --- |
  | 1 | ID 1 Mai Chi (27/27 crops, best 0.72, from 6.4 s); ID 2 Thuận Minh (22/22, 0.73, 20.9 s); ID 3 Đức Mạnh (19/20, 0.79, 31.8 s); ID 4 Hồng Minh (18/19, 0.65, 42.5 s) | cam_1 IDs 5, 7, 12, 17; cam_2 IDs 5, 6, 16, 25 (same order) |
  | 2 | ID 1 unknown (0 face crops) | – |
  | 3 | ID 1 Đức Mạnh (46/59, 0.76, 11.3 s); ID 2 Thuận Minh (59/59, 0.80, 11.3 s); ID 3 Hồng Minh (41/52, 0.58, 12.4 s); ID 5 Đức Mạnh (4/4, 0.65, 23.1 s) | not carried: 3 people at the door together (link_names skips ambiguous cases) |
  | 4 | ID 1 Hồng Minh (34/48, 0.65, 9.4 s) | cam_1 ID 4, cam_2 ID 11 |
  | 5 | ID 1 unknown (0 face crops) | – |
  | 6 | ID 1 unknown (0 face crops) | – |
  | 7 | IDs 1, 2 unknown (3 and 0 face crops; 1 weak match, 0.41) | – |
  | 8 | ID 1 Hồng Minh (6/7, 0.49, 5.4 s) | cam_1 ID 7, cam_2 ID 6 |

  Takes 1 and 3 agree with the ground-truth clothing: red jersey (P1) = Thuận Minh, grey T-shirt (P2) =
  Đức Mạnh, navy #27 (P3) = Hồng Minh, P4 = Mai Chi. Take 3 checked by eye on frames at 16, 20 and 23.5 s:
  all three boxes carry the right name. ID 5 (22.7–24.8 s) is Đức Mạnh again walking through the door after
  ID 1 ends at 22.3 s: a tracker ID switch, not a wrong name. Take 1 checked by eye the same way: all four
  attendance names and all eight cam_1 / cam_2 handoffs are the right person. After they sit down,
  Thuận Minh and Đức Mạnh get new unnamed IDs (cam_2 IDs 18 and 17, cam_1 ID 18 through the glass), the
  known "later tracks of the same person" gap in `ml/tracking/README.md`. Takes 2, 5, 6 and 7 stay
  unknown: no usable face (the person passes side-on or with their back to the camera).
- **Result (takes 1–8, 2026-11-17, Mai Chi only enrolled):** take 1 track 1 (Mai Chi walking in) matched in 27/27 face crops (best cosine
  0.72), named from 6.4 s (ground-truth check-in 7.0 s). No other track matched: 0 of 293 face crops on
  every other track (P1–P3 and the people in takes 3–8) passed the threshold.
- **cam_1 / cam_2:** `ml/tracking/link_names.py` carries the name to the track that is at the door at
  check-in (door handoff); see `ml/tracking/README.md` section 4.
