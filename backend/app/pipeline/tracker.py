"""Single-camera tracking (task T5).  Owner: Mai Chi

Keeps a stable local track ID per person inside one camera.
"""


class CameraTracker:
    def __init__(self, cam_id):
        self.cam_id = cam_id

    def update(self, detections, timestamp):
        """Return [{"local_id": int, "box": (x, y, w, h)}, ...].

        TODO: ByteTrack (ultralytics `model.track(..., tracker="bytetrack.yaml")` is the quickest start).
        """
        raise NotImplementedError
