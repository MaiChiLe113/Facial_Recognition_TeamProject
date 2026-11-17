"""Precompute person boxes + track IDs for one recorded video.  Owner: Mai Chi

Output: data/tracks/<cam_id>.json in the format the frontend already draws
(see the README "Data contract for bounding boxes"). The backend serves it
automatically instead of the mock file once it exists.

Usage (from the repo root, with the ml/.venv environment):
    ml/.venv/bin/pip install -r ml/tracking/requirements.txt
    ml/.venv/bin/python ml/tracking/precompute_tracks.py --cam all
    ml/.venv/bin/python ml/tracking/precompute_tracks.py --cam cam_1 --tracker ml/tracking/configs/bytetrack_long.yaml

Videos come from paths.py (the 30 fps MP4 in data/raw/converted/ when present, else the .webm).
"""
import argparse
import csv
import json
import time
from pathlib import Path

import cv2

from paths import camera_ids, configured_take, video_path

REPO = Path(__file__).resolve().parents[2]
SOURCE = "yolo11n+bytetrack"


def video_fps(video_path):
    """FPS of the processed file; browser .webm files may report 0 or 1000 fps -> fall back to 30."""
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return fps if 1 <= fps <= 120 else 30.0


def to_box(cx, cy, w, h, frame_w, frame_h):
    """Centre-based pixel xywh -> [x, y, w, h] fractions of the frame, x, y = top-left, clipped to the frame."""
    x0, y0 = max(0.0, cx - w / 2), max(0.0, cy - h / 2)
    x1, y1 = min(float(frame_w), cx + w / 2), min(float(frame_h), cy + h / 2)
    return [round(x0 / frame_w, 4), round(y0 / frame_h, 4), round((x1 - x0) / frame_w, 4), round((y1 - y0) / frame_h, 4)]


def run(cam_id, video_path, every_n=3, model_name="yolo11n.pt", conf=0.4, min_keyframes=5,
        tracker="bytetrack.yaml", out_dir=None, device=None):
    tracks = {}  # track_id -> {"global_id": ..., "name": None, "keyframes": [...]}

    # TODO 1: load a small person detector.
    # A fresh model per video: with persist=True one model would carry ByteTrack state (and IDs) across cameras.
    import torch
    from ultralytics import YOLO
    # attendance_cam uses the same person detector for now: face detector replaces this later
    local = Path(__file__).resolve().parent / model_name  # weights downloaded next to this script (git-ignored)
    model = YOLO(str(local) if local.exists() else model_name)
    if device is None:
        device = "mps" if torch.backends.mps.is_available() else "cpu"

    # TODO 3: time in seconds from the FPS of the file actually processed.
    fps = video_fps(video_path)

    # TODO 2: run detection + tracking over the video, frame by frame (people only, ByteTrack, persistent IDs).
    raw_ids = set()
    frame_index = -1
    t0 = time.perf_counter()
    for frame_index, result in enumerate(model.track(source=str(video_path), stream=True, tracker=str(tracker),
                                                     classes=[0], persist=True, conf=conf, device=device,
                                                     verbose=False)):
        if result.boxes.id is None:  # detections without a track ID are skipped
            continue
        ids = [int(i) for i in result.boxes.id.tolist()]
        raw_ids.update(ids)
        if frame_index % every_n:
            continue
        t = frame_index / fps
        frame_h, frame_w = result.orig_shape
        for track_id, (cx, cy, w, h) in zip(ids, result.boxes.xywh.tolist()):
            # TODO 4: convert each box to fractions of the frame: [x, y, w, h] with x, y = top-left.
            box = to_box(cx, cy, w, h, frame_w, frame_h)
            # TODO 5: append the keyframe. For now global_id = track_id; matcher.py replaces it later.
            entry = tracks.setdefault(track_id, {"global_id": track_id, "name": None, "keyframes": []})
            entry["keyframes"].append({"t": round(t, 2), "box": box})
    elapsed = time.perf_counter() - t0
    frames = frame_index + 1

    kept = [tr for tr in tracks.values() if len(tr["keyframes"]) >= min_keyframes]
    kept.sort(key=lambda tr: (tr["keyframes"][0]["t"], tr["global_id"]))
    keyframes = sum(len(tr["keyframes"]) for tr in kept)
    times = [kf["t"] for tr in kept for kf in tr["keyframes"]]

    out = {"cam_id": cam_id, "source": SOURCE, "tracks": kept}
    out_path = Path(out_dir or REPO / "data" / "tracks") / f"{cam_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")

    stats = {
        "cam_id": cam_id, "tracker": Path(tracker).stem, "video": Path(video_path).name, "device": device,
        "frames": frames, "fps_video": fps, "ids_raw": len(raw_ids),
        "ids_with_keyframes": len(tracks), "ids_kept": len(kept), "ids_dropped": len(raw_ids) - len(kept),
        "keyframes": keyframes, "t_min": min(times, default=None), "t_max": max(times, default=None),
        "proc_fps": round(frames / elapsed, 1) if elapsed else None, "out": out_path,
    }
    print(f"{cam_id}: {stats['ids_raw']} raw IDs -> kept {len(kept)} (dropped {stats['ids_dropped']}), "
          f"{keyframes} keyframes, t {stats['t_min']}-{stats['t_max']} s, {frames} frames at {stats['proc_fps']} fps "
          f"on {device} -> {out_path.relative_to(REPO) if out_path.is_relative_to(REPO) else out_path}")
    return stats


def append_eval_rows(csv_path, rows, real_people):
    """Append one row per camera to the E1 baseline CSV (keeps existing rows)."""
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["cam_id", "tracker", "ids_raw", "ids_kept", "real_people", "fps"])
        for s in rows:
            w.writerow([s["cam_id"], s["tracker"], s["ids_raw"], s["ids_kept"], real_people.get(s["cam_id"], ""),
                        s["proc_fps"]])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cam", default="all", choices=["cam_1", "cam_2", "attendance_cam", "all"])
    p.add_argument("--take", type=int, default=None, help="take number (default: the take in data/video_config.json)")
    p.add_argument("--every-n", type=int, default=3, help="keep every Nth frame as a keyframe")
    p.add_argument("--model", default="yolo11n.pt")
    p.add_argument("--conf", type=float, default=0.4)
    p.add_argument("--min-keyframes", type=int, default=5, help="drop tracks with fewer keyframes")
    p.add_argument("--tracker", default="bytetrack.yaml",
                   help="Ultralytics tracker name or YAML path, e.g. ml/tracking/configs/bytetrack_long.yaml")
    p.add_argument("--out-dir", default=None, help="where to write <cam_id>.json (default: data/tracks/)")
    p.add_argument("--eval-csv", default=None, help="append per-camera counts to this CSV (e.g. data/eval/tracking_baseline.csv)")
    p.add_argument("--real-people", nargs="*", default=[], metavar="CAM=N",
                   help="human-counted people per camera for --eval-csv, e.g. cam_1=4")
    a = p.parse_args()

    take = configured_take() if a.take is None else a.take
    cams = camera_ids() if a.cam == "all" else [a.cam]
    print(f"take {take}, tracker {a.tracker}, model {a.model}, conf {a.conf}, every_n {a.every_n}, "
          f"min_keyframes {a.min_keyframes}")
    all_stats = [run(cam, video_path(cam, take), a.every_n, a.model, a.conf, a.min_keyframes, a.tracker, a.out_dir)
                 for cam in cams]
    if a.eval_csv:
        real = {k: int(v) for k, v in (x.split("=", 1) for x in a.real_people)}
        append_eval_rows(a.eval_csv, all_stats, real)
        print(f"Appended {len(all_stats)} rows to {a.eval_csv}")
