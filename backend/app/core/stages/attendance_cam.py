"""The attendance camera: find the face, check liveness, recognise it, read the emotion.
Adapters only: the models are in app/pipeline/detector.py (Mai Chi), liveness.py (Hồng Minh),
recognizer.py (Thuận Minh) and emotion.py (Minh Thành)."""
from collections import deque

from ..registry import register_stage
from .base import Stage


def _crop(image, box):
    x, y, w, h = (int(v) for v in box[:4])
    return image[max(y, 0):y + h, max(x, 0):x + w] if hasattr(image, "shape") else None


@register_stage("detect_faces")
class DetectFaces(Stage):
    def setup(self):
        from ...pipeline import detector
        self.detector = detector

    def process(self, ctx):
        ctx.faces = [{"box": tuple(d[:4]), "score": d[4] if len(d) > 4 else None, "crop": _crop(ctx.image, d)}
                     for d in self.detector.detect_faces(ctx.image)]


@register_stage("liveness")
class Liveness(Stage):
    """liveness.check() wants ~10 recent crops of one face. Options: {"frames": 10}.
    TODO: keep one buffer per global ID once the matcher links faces to tracks; for now one
    buffer for the main (largest) face, which is enough for one person at the door."""

    def setup(self):
        from ...pipeline import liveness
        self.liveness = liveness
        self.recent = deque(maxlen=int(self.options.get("frames", 10)))

    def process(self, ctx):
        faces = [f for f in ctx.faces if f["crop"] is not None]
        if not faces:
            self.recent.clear()
            return
        main = max(faces, key=lambda f: f["box"][2] * f["box"][3])
        self.recent.append(main["crop"])
        result = self.liveness.check(list(self.recent))
        main["live"], main["liveness_score"] = bool(result["live"]), result.get("score")


@register_stage("recognize")
class Recognize(Stage):
    """Options: {"threshold": <from the ROC>}. The gallery {student_id: [embeddings]} is read from
    shared["gallery"]; TODO (Đức Mạnh): fill it from the face_embeddings table when the DB is wired."""

    def setup(self):
        from ...pipeline import recognizer
        self.recognizer = recognizer
        self.threshold = self.options.get("threshold")

    def process(self, ctx):
        gallery = self.shared.get("gallery", {})
        for face in ctx.faces:
            if face.get("live") is False or face["crop"] is None:
                continue                       # never identify a spoof
            face["student_id"], face["similarity"] = self.recognizer.identify(face["crop"], gallery, self.threshold)


@register_stage("emotion")
class Emotion(Stage):
    def setup(self):
        from ...pipeline import emotion
        self.emotion = emotion

    def process(self, ctx):
        for face in ctx.faces:
            if face["crop"] is None:
                continue
            result = self.emotion.predict(face["crop"])
            face["emotion"], face["emotion_score"] = result["label"], result.get("score")
