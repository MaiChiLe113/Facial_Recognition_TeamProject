"""The liveness stage checks every face, each with its own buffer (a face on a phone screen is smaller than the
person holding the phone and used to be left unchecked, then recognised as live)."""
import numpy as np

from app.core.stages import attendance_cam
from app.core.stages.attendance_cam import Liveness
from app.core.types import FrameContext


class FakeInfer:
    """live when the crop's pixels are bright; records how many crops each call got."""
    def __init__(self):
        self.sizes = []

    def check(self, crops):
        self.sizes.append(len(crops))
        score = float(np.mean([c.mean() for c in crops])) / 255
        return {"live": score >= 0.5, "score": score}


def make_stage(monkeypatch):
    infer = FakeInfer()
    monkeypatch.setattr(attendance_cam, "load_infer", lambda name: infer)
    stage = Liveness("cam", "attendance", {}, {})
    stage.setup()
    return stage, infer


def face(box, value):
    crop = np.full((8, 8, 3), value, np.uint8)
    return {"box": box, "crops": {"anti_spoofing": crop}}


def ctx_with(*faces):
    ctx = FrameContext.__new__(FrameContext)
    ctx.faces = list(faces)
    return ctx


def test_every_face_is_checked(monkeypatch):
    stage, _ = make_stage(monkeypatch)
    real, phone = face((0, 0, 200, 200), 250), face((250, 50, 60, 60), 10)
    stage.process(ctx_with(real, phone))
    assert real["live"] is True
    assert phone["live"] is False


def test_each_face_keeps_its_own_buffer(monkeypatch):
    stage, infer = make_stage(monkeypatch)
    for _ in range(3):
        stage.process(ctx_with(face((0, 0, 200, 200), 250), face((250, 50, 60, 60), 10)))
    assert max(infer.sizes) == 3 and len(stage.tracks) == 2


def test_missing_crop_is_never_live(monkeypatch):
    stage, _ = make_stage(monkeypatch)
    f = {"box": (0, 0, 50, 50), "crops": {"anti_spoofing": None}}
    stage.process(ctx_with(f))
    assert f["live"] is False and f["liveness_score"] == 0.0


def test_buffer_is_dropped_after_the_face_leaves(monkeypatch):
    stage, _ = make_stage(monkeypatch)
    stage.process(ctx_with(face((0, 0, 100, 100), 250)))
    for _ in range(stage.max_missed + 1):
        stage.process(ctx_with())
    assert stage.tracks == []


def test_spoof_gets_no_emotion(monkeypatch):
    from app.core.stages.attendance_cam import Emotion
    seen = []

    class Feel:
        def predict(self, crop, smooth=False):
            seen.append(crop)
            return {"scores": {"sad": 1.0}}

    monkeypatch.setattr(attendance_cam, "load_infer", lambda name: Feel())
    stage = Emotion("cam", "attendance", {}, {})
    stage.setup()
    real = {"box": (0, 0, 100, 100), "live": True, "crops": {"emotion": np.zeros((8, 8, 3), np.uint8)}}
    phone = {"box": (200, 0, 150, 150), "live": False, "crops": {"emotion": np.zeros((8, 8, 3), np.uint8)}}
    ctx = ctx_with(real, phone)
    ctx.t = 0.0
    stage.process(ctx)
    assert "emotion" in real and "emotion" not in phone and len(seen) == 1


def test_several_faces_with_different_crop_sizes(monkeypatch):
    """Regression: buffers were removed from the free list with list.remove(), which compares the buffers' numpy
    crops with == and raised "operands could not be broadcast" once two faces of different sizes were followed
    (three students at the doorway in take 3 made the stage fail on every frame)."""
    stage, _ = make_stage(monkeypatch)
    small = lambda: {"box": (250, 50, 60, 60), "crops": {"anti_spoofing": np.full((6, 6, 3), 10, np.uint8)}}
    big = lambda: {"box": (0, 0, 200, 200), "crops": {"anti_spoofing": np.full((9, 9, 3), 250, np.uint8)}}
    stage.process(ctx_with(small()))                 # the small face gets the first buffer
    for _ in range(12):                              # both buffers full (10 crops): deques of equal length compare
        b, s = big(), small()
        stage.process(ctx_with(s, b))
        assert b["live"] is True and s["live"] is False
    assert len(stage.tracks) == 2
