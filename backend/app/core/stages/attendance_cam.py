"""Face stages: find the face, check liveness, recognise it, read the emotion. They run on every camera
(pipeline.json), but only the attendance camera's results become check-ins (see emit.py).
Adapters only: the face detector is app/pipeline/detector.py (Mai Chi); the three models live in
ml/anti_spoofing/ (Hồng Minh), ml/face_recognition/ (Thuận Minh) and ml/emotion/ (Minh Thành), each as
infer.py plus <feature>.pt, found by app/core/ml_models.py.

Each face is cut out once per model with that model's margin (ml_models.MARGIN, the same crops as the Features demo):
face["crops"] = {"face_recognition": ..., "anti_spoofing": ..., "emotion": ...} (None when empty)."""
from collections import deque

from ..ml_models import FEATURES, crop_face, load_infer
from ..registry import register_stage
from .base import Stage


def _crops(image, box):
    return {feature: crop_face(image, box, feature) for feature in FEATURES}


@register_stage("detect_faces")
class DetectFaces(Stage):
    def setup(self):
        from ...pipeline import detector
        self.detector = detector

    def process(self, ctx):
        ctx.faces = [{"box": tuple(d[:4]), "score": d[4] if len(d) > 4 else None, "crops": _crops(ctx.image, d)}
                     for d in self.detector.detect_faces(ctx.image)]


@register_stage("liveness")
class Liveness(Stage):
    """liveness.check() wants ~10 recent crops of one face. Options: {"frames": 10}.
    TODO: keep one buffer per global ID once the matcher links faces to tracks; for now one
    buffer for the main (largest) face, which is enough for one person at the door."""

    def setup(self):
        self.liveness = load_infer("anti_spoofing")
        self.recent = deque(maxlen=int(self.options.get("frames", 10)))

    def process(self, ctx):
        faces = [f for f in ctx.faces if f["crops"]["anti_spoofing"] is not None]
        if not faces:
            self.recent.clear()
            return
        main = max(faces, key=lambda f: f["box"][2] * f["box"][3])
        self.recent.append(main["crops"]["anti_spoofing"])
        result = self.liveness.check(list(self.recent))
        main["live"], main["liveness_score"] = bool(result["live"]), result.get("score")


@register_stage("recognize")
class Recognize(Stage):
    """Options: {"threshold": <from the ROC>}. The gallery {student_id: [embeddings]} is read from
    shared["gallery"], which app/services/gallery.py keeps up to date (gallery.attach(engine) in main.py)."""

    def setup(self):
        self.recognizer = load_infer("face_recognition")
        self.threshold = self.options.get("threshold")

    def process(self, ctx):
        gallery = self.shared.get("gallery", {})
        for face in ctx.faces:
            crop = face["crops"]["face_recognition"]
            if face.get("live") is False or crop is None:
                continue                       # never identify a spoof
            face["student_id"], face["similarity"] = self.recognizer.identify(crop, gallery, self.threshold)


@register_stage("emotion")
class Emotion(Stage):
    """The emotion infer.py smooths over one module-wide buffer, which would mix the cameras' faces. This stage is
    one instance per camera, so it asks for the raw probabilities and averages the last SMOOTH_S seconds itself."""
    SMOOTH_S = 1.0

    def setup(self):
        self.emotion = load_infer("emotion")
        self.recent = deque()           # (t, {label: prob}) of this camera's main face

    def process(self, ctx):
        faces = [f for f in ctx.faces if f["crops"]["emotion"] is not None]
        if not faces:
            self.recent.clear()
            return
        main = max(faces, key=lambda f: f["box"][2] * f["box"][3])
        for face in faces:
            scores = self.emotion.predict(face["crops"]["emotion"], smooth=False)["scores"]
            if face is main:
                self.recent.append((ctx.t, scores))
                while self.recent and ctx.t - self.recent[0][0] > self.SMOOTH_S:
                    self.recent.popleft()
                scores = {k: sum(s[k] for _, s in self.recent) / len(self.recent) for k in scores}
            label = max(scores, key=scores.get)
            face["emotion"], face["emotion_score"] = label, scores[label]
