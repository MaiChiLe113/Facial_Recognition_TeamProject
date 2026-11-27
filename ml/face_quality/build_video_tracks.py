"""Pack the recorded takes' track boxes into one small file for 05_finetune_video.ipynb (Colab).

Reads data/video_config.json (which video file is which take and camera) and data/tracks/take<N>/<cam>.json (YOLO11n +
ByteTrack person boxes, see ml/tracking). Writes ml/face_quality/video_tracks.json:

    {"takes": [{"take": 1, "files": {"cam_1": "...webm", ...},
                "tracks": {"cam_1": [{"id": 3, "kf": [[t, x, y, w, h], ...]}, ...], ...}}, ...]}

Boxes are normalised to the frame (0..1), t in seconds from the start of that camera's file. Names are left out on
purpose: the notebook names faces itself, with an independent recogniser (SFace), so its labels do not depend on the
team recogniser it is computing them with.

    python ml/face_quality/build_video_tracks.py
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main():
    config = json.loads((REPO / "data" / "video_config.json").read_text(encoding="utf-8"))
    takes = []
    for take in config["takes"]:
        n = take["take"]
        tracks = {}
        for cam in take["files"]:
            path = REPO / "data" / "tracks" / f"take{n}" / f"{cam}.json"
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            tracks[cam] = [{"id": tr["global_id"],
                            "kf": [[round(k["t"], 2), *[round(v, 4) for v in k["box"]]] for k in tr["keyframes"]]}
                           for tr in data["tracks"]]
        takes.append({"take": n, "files": take["files"], "tracks": tracks})
    out = REPO / "ml" / "face_quality" / "video_tracks.json"
    out.write_text(json.dumps({"takes": takes}, separators=(",", ":")), encoding="utf-8")
    n_tracks = sum(len(v) for t in takes for v in t["tracks"].values())
    print(f"{out.relative_to(REPO)}: {len(takes)} takes, {n_tracks} tracks, {out.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
