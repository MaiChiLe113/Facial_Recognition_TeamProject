"""Precompute person boxes + track IDs for one recorded video.  Owner: Mai Chi

Output: data/tracks/<cam_id>.json in the format the frontend already draws
(see the README "Data contract for bounding boxes"). The backend serves it
automatically instead of the mock file once it exists.

Usage (from the repo root):
    pip install ultralytics opencv-python
    python ml/tracking/precompute_tracks.py --cam cam_1 --video "<path to .webm>"

This file is a skeleton with hints. Fill in the TODOs yourself.
"""
import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run(cam_id, video_path, every_n=3):
    tracks = {}  # track_id -> {"global_id": ..., "name": None, "keyframes": [...]}

    # TODO 1: load a small person detector.
    #   Hint: from ultralytics import YOLO; model = YOLO("yolov8n.pt")

    # TODO 2: run detection + tracking over the video, frame by frame.
    #   Hint: model.track(source=video_path, stream=True, tracker="bytetrack.yaml",
    #                     classes=[0], persist=True)  -> one result per frame
    #   Each result has: result.orig_shape (h, w), result.boxes.xywh, result.boxes.id

    # TODO 3: for every Nth frame (every_n), work out the time in seconds.
    #   Hint: t = frame_index / fps   (fps from cv2.VideoCapture(video_path).get(cv2.CAP_PROP_FPS);
    #   .webm files from the browser may report 0 or 1000 fps -> check, and fall back to 30)

    # TODO 4: convert each box to fractions of the frame: [x, y, w, h] with x, y = top-left.
    #   Hint: xywh from YOLO is the CENTRE x, y. x_left = (cx - w/2) / frame_w

    # TODO 5: append {"t": round(t, 2), "box": [...]} to tracks[track_id]["keyframes"].
    #   For now global_id = track_id. Cross-camera matching (matcher.py) replaces it later.

    out = {"cam_id": cam_id, "source": "yolov8n+bytetrack", "tracks": list(tracks.values())}
    out_path = REPO / "data" / "tracks" / f"{cam_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"Wrote {len(tracks)} tracks to {out_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cam", required=True, choices=["cam_1", "cam_2", "attendance_cam"])
    p.add_argument("--video", required=True)
    p.add_argument("--every-n", type=int, default=3)
    a = p.parse_args()
    run(a.cam, a.video, a.every_n)
