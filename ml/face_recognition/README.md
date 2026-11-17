# Face recognition — Owner: Thuận Minh

- [ ] Download the Kaggle dataset into `data/raw/` (git-ignored)
- [ ] `train_classification.py` — ResNet-18 → 512-d → softmax, cross-entropy
- [ ] `train_triplet.py` — same backbone, triplet loss, semi-hard mining
- [ ] `evaluate.py` — ROC/AUC on `verification_pairs_val.txt`, cosine vs Euclidean, pick threshold
- [ ] Export the chosen model for `backend/app/pipeline/recognizer.py`

Results: _TBC_

## Baseline in use now: `name_tracks.py`

Until the models above are trained, the demo names people with OpenCV's pre-trained **YuNet** (face
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

- **Enrolment:** every student in `data/mock/students.csv` with photos: the files in `photo_folder` and the
  `student_card` image (paths relative to the Drive folder that holds `AppliedML/`; HEIC is converted
  with macOS `sips` into `data/raw/enrol/`). Le Mai Chi: 8 usable faces from 15 photos + the card (the
  other 8 photos show her with a face mask and no face is detected). The other students have no photos yet.
- **Matching:** each `attendance_cam` track is named when at least 3 face crops inside its box match one
  student. `name_from` = time of the 3rd match, so the UI shows `ID n · Unknown` until check-in and
  `ID n · Mai Chi` after it.
- **Result (takes 1–8):** take 1 track 1 (Mai Chi walking in) matched in 27/27 face crops (best cosine
  0.72), named from 6.4 s (ground-truth check-in 7.0 s). No other track matched: 0 of 293 face crops on
  every other track (P1–P3 and the people in takes 3–8) passed the threshold.
- **cam_1 / cam_2:** `ml/tracking/link_names.py` carries the name to the track that is at the door at
  check-in (door handoff); see `ml/tracking/README.md` section 4.
