"""Name people on the attendance camera from their enrolment photos (baseline).  Owner: Thuận Minh / Mai Chi

Stand-in for the trained face model until train_classification.py / train_triplet.py exist:
OpenCV's pre-trained YuNet (face detection) + SFace (128-d face embedding, cosine similarity).

1. Enrol: for every student in data/mock/students.csv, embed the faces in their photo folder and on their
   student card (both paths are relative to the folder that holds AppliedML/, i.e. HAWKEYE_VIDEO_ROOT/../..).
2. Match: for every attendance_cam track in data/tracks/take<N>/attendance_cam.json, embed the faces that
   fall inside the track box, compare with every enrolled face, and write the student's name into the
   track's "name" field when enough frames agree, plus "name_from": the time (s) of the MIN_MATCHED_FRAMES-th
   matching frame, i.e. when the check-in is confident (the UI shows "Unknown" before it). Tracks that match
   nobody keep name = null.

3. Carry each name to cam_1 / cam_2 (ml/tracking/link_names.py, door handoff).

Run after precompute_tracks.py (it rewrites the track files and resets every name):
    ml/.venv/bin/python ml/face_recognition/name_tracks.py --take all

Models (git-ignored, ml/face_recognition/models/), from github.com/opencv/opencv_zoo:
    face_detection_yunet_2023mar.onnx, face_recognition_sface_2021dec.onnx
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ml" / "tracking"))
from link_names import link_take  # noqa: E402
from paths import configured_take, video_config, video_path, video_root  # noqa: E402

MODELS = Path(__file__).resolve().parent / "models"
ENROL_CACHE = REPO / "data" / "raw" / "enrol"          # HEIC -> JPEG copies (git-ignored)
MATCH_THRESHOLD = 0.363       # SFace cosine threshold recommended by OpenCV (LFW, FAR ~ 1e-3)
MIN_MATCHED_FRAMES = 3        # a track is named only if at least this many of its face crops match
MIN_FACE_PX = 40              # ignore faces smaller than this (too blurry to embed)
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic"}


class FaceModel:
    def __init__(self):
        self.det = cv2.FaceDetectorYN.create(str(MODELS / "face_detection_yunet_2023mar.onnx"), "", (320, 320), 0.8)
        self.rec = cv2.FaceRecognizerSF.create(str(MODELS / "face_recognition_sface_2021dec.onnx"), "")

    def faces(self, img):
        """YuNet detections (rows of 15 numbers: box, 5 landmarks, score), largest first."""
        h, w = img.shape[:2]
        self.det.setInputSize((w, h))
        _, found = self.det.detect(img)
        if found is None:
            return []
        return sorted(found, key=lambda f: -f[2] * f[3])

    def embed(self, img, face):
        feat = self.rec.feature(self.rec.alignCrop(img, face))
        return feat / np.linalg.norm(feat)


def read_image(path):
    """cv2 image; HEIC photos are converted once with macOS `sips` into data/raw/enrol/."""
    if path.suffix.lower() == ".heic":
        out = ENROL_CACHE / path.parent.name / (path.stem + ".jpg")
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["sips", "-s", "format", "jpeg", str(path), "--out", str(out)], check=True, capture_output=True)
        path = out
    img = cv2.imread(str(path))
    if img is not None and max(img.shape[:2]) > 1600:          # phone photos: faster detection, same result
        s = 1600 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=s, fy=s)
    return img


def enrol(model):
    """{student_id_vn: {"name", "embeddings": [n, 128], "sources": [...]}} for students with photos."""
    drive = video_root().parent.parent           # .../My Drive (holds AppliedML/)
    gallery = {}
    for s in csv.DictReader((REPO / "data" / "mock" / "students.csv").open(encoding="utf-8")):
        files = []
        folder = drive / s["photo_folder"] if s.get("photo_folder") else None
        if folder and folder.is_dir():
            files += sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT)
        if s.get("student_card"):
            files.append(drive / s["student_card"])
        embs, used = [], []
        for f in files:
            img = read_image(f) if f.exists() else None
            found = model.faces(img) if img is not None else []
            if not found:
                print(f"  {s['student_name']}: no face in {f.name}")
                continue
            embs.append(model.embed(img, found[0]))
            used.append(f.name)
        if embs:
            gallery[s["student_id_vn"]] = {"name": s["student_name"], "embeddings": np.vstack(embs), "sources": used}
        print(f"enrolled {s['student_name']}: {len(embs)} faces from {len(files)} files")
    return gallery


def name_take(model, gallery, take, every=2):
    """Match the attendance_cam tracks of one take; rewrite its JSON with names. Returns a summary list."""
    path = REPO / "data" / "tracks" / f"take{take}" / "attendance_cam.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    cap = cv2.VideoCapture(str(video_path("attendance_cam", take)))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    summary = []
    for tr in data["tracks"]:
        votes = {}                                   # student_id -> list of (t, similarity) for matching frames
        crops = 0
        for kf in tr["keyframes"][::every]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, round(kf["t"] * fps))
            ok, frame = cap.read()
            if not ok:
                continue
            H, W = frame.shape[:2]
            x, y, w, h = kf["box"]
            bx0, by0, bx1, by1 = x * W, y * H, (x + w) * W, (y + h) * H
            for face in model.faces(frame):
                cx, cy = face[0] + face[2] / 2, face[1] + face[3] / 2
                if face[2] < MIN_FACE_PX or not (bx0 <= cx <= bx1 and by0 <= cy <= by1):
                    continue
                crops += 1
                e = model.embed(frame, face)
                for sid, g in gallery.items():
                    sim = float(np.max(g["embeddings"] @ e.T))
                    if sim >= MATCH_THRESHOLD:
                        votes.setdefault(sid, []).append((kf["t"], sim))
                break                                # one face per box
        best = max(votes, key=lambda k: len(votes[k]), default=None)
        name = gallery[best]["name"] if best and len(votes[best]) >= MIN_MATCHED_FRAMES else None
        tr["name"] = name
        tr.pop("name_from", None)
        if name:
            tr["name_from"] = votes[best][MIN_MATCHED_FRAMES - 1][0]
        summary.append({"take": take, "track": tr["global_id"], "face_crops": crops,
                        "matches": {gallery[k]["name"]: len(v) for k, v in votes.items()},
                        "best_sim": round(max(s for _, s in votes[best]), 3) if best else None, "name": name,
                        "name_from": tr.get("name_from")})
    cap.release()
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--take", default=None, help="take number or 'all' (default: the configured take)")
    a = p.parse_args()
    takes = ([t["take"] for t in video_config()["takes"]] if a.take == "all"
             else [configured_take() if a.take is None else int(a.take)])
    model = FaceModel()
    gallery = enrol(model)
    for t in takes:
        for s in name_take(model, gallery, t):
            print(f"take {s['take']} attendance_cam track {s['track']}: {s['face_crops']} face crops, "
                  f"matches {s['matches']}, best {s['best_sim']} -> {s['name'] or 'unknown'}"
                  + (f" from t={s['name_from']} s" if s["name_from"] is not None else ""))
        for line in link_take(t):
            print(line)
