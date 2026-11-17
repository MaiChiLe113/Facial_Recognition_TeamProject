# Tracking (Mai Chi)

Person detection + tracking for the three demo cameras. Output feeds the Home page through
`GET /api/tracks/{cam_id}` (see the root README, "Data contract for bounding boxes").
Step A5 extends this file with setup, conversion and ground-truth instructions.

## Precompute the demo tracks

```bash
ml/.venv/bin/python ml/tracking/precompute_tracks.py --cam all \
    --tracker ml/tracking/configs/bytetrack_long.yaml
```

Writes `data/tracks/{cam_1,cam_2,attendance_cam}.json` (committed; the demo needs them).
Defaults: `yolo11n.pt` (pre-trained, not fine-tuned), class 0 (person), `conf 0.4`,
keyframe every 3rd frame, tracks with fewer than 5 keyframes dropped. `global_id` is the
camera-local ByteTrack ID until cross-camera matching replaces it.

## Tracker choice (E1 baseline, take 4)

The committed `data/tracks/` files come from **`configs/bytetrack_long.yaml`**: Ultralytics'
`bytetrack.yaml` with `track_buffer: 90` instead of 30, so a lost person is kept alive for ~3 s
at 30 fps instead of ~1 s.

| cam_id | tracker | IDs before filtering | IDs kept | real people |
| --- | --- | --- | --- | --- |
| cam_1 | bytetrack | 20 | 16 | 4 |
| cam_1 | bytetrack_long | 17 | 13 | 4 |
| cam_2 | bytetrack | 24 | 15 | not counted |
| cam_2 | bytetrack_long | 20 | 14 | not counted |
| attendance_cam | bytetrack | 5 | 4 | not counted |
| attendance_cam | bytetrack_long | 5 | 4 | not counted |

Why `bytetrack_long`: with no frame-level ground truth yet, ID switches cannot be measured
directly. The proxy used is extra IDs = IDs kept − real people. On cam_1 (4 people, counted by
watching the annotated video) that is 12 for `bytetrack` and 9 for `bytetrack_long`; it also
produces fewer IDs on cam_2 and the same on attendance_cam. Both are still far above 4, so each
person is split into several IDs: cross-camera matching / Re-ID has to merge them.

Full numbers incl. processing fps: `data/eval/tracking_baseline.csv`. Reproduce with
`--out-dir runs/compare/<name> --eval-csv data/eval/tracking_baseline.csv --real-people cam_1=4`.
