"""Single-camera tracking (task T5).  Owner: Mai Chi

Keeps a stable local track ID per person inside one camera: ByteTrack (Ultralytics) fed with the boxes from
detector.detect_people, with the same settings as the precomputed demo tracks (ml/tracking/configs/bytetrack_long.yaml).

That config keeps a lost person for 90 frames = 3 s at the recordings' 30 fps. Live camera streams run slower and
unevenly (a phone sends ~5-10 frames a second), so the 3 s are converted to frames from the measured frame rate.
"""
from types import SimpleNamespace

from ..config import REPO_DIR

CONFIG = REPO_DIR / "ml" / "tracking" / "configs" / "bytetrack_long.yaml"
RECORDED_FPS = 30.0          # the frame rate bytetrack_long.yaml's track_buffer was chosen for


def _settings():
    import yaml
    return SimpleNamespace(**yaml.safe_load(CONFIG.read_text(encoding="utf-8")))


class _Detections:
    """The results-like object BYTETracker reads: centre-xywh boxes, scores and classes, boolean-indexable."""

    def __init__(self, xywh, conf):
        import numpy as np
        self.xywh, self.conf, self.cls = xywh, conf, np.zeros(len(conf), dtype=np.float32)

    def __len__(self):
        return len(self.conf)

    def __getitem__(self, mask):
        return _Detections(self.xywh[mask], self.conf[mask])


class CameraTracker:
    def __init__(self, cam_id):
        from ultralytics.trackers.byte_tracker import BYTETracker
        self.cam_id = cam_id
        self.settings = _settings()
        self.buffer_seconds = self.settings.track_buffer / RECORDED_FPS
        self.tracker = BYTETracker(self.settings)
        self.last_t = None
        self.fps = RECORDED_FPS

    def _keep_lost_for(self, timestamp):
        """Update the measured frame rate and keep lost tracks for buffer_seconds at that rate."""
        if self.last_t is not None and timestamp > self.last_t:
            self.fps = 0.8 * self.fps + 0.2 * (1.0 / (timestamp - self.last_t))
        self.last_t = timestamp
        self.tracker.max_frames_lost = max(1, round(self.buffer_seconds * self.fps))

    def update(self, detections, timestamp):
        """detections: [(x, y, w, h, score), ...] in pixels (top-left corner).
        Returns [{"local_id": int, "box": (x, y, w, h), "score": float}, ...] for the people tracked on this frame."""
        import numpy as np
        self._keep_lost_for(timestamp)
        d = np.asarray([det[:5] for det in detections], dtype=np.float32).reshape(-1, 5)
        xywh = np.column_stack([d[:, 0] + d[:, 2] / 2, d[:, 1] + d[:, 3] / 2, d[:, 2], d[:, 3]])
        rows = self.tracker.update(_Detections(xywh, d[:, 4]))          # [x1, y1, x2, y2, id, score, cls, idx]
        return [{"local_id": int(r[4]), "box": (float(r[0]), float(r[1]), float(r[2] - r[0]), float(r[3] - r[1])),
                 "score": float(r[5])} for r in rows]
