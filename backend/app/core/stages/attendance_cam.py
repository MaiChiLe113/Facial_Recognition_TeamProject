"""Face stages: find the face, check liveness, recognise it, read the emotion. They run on every camera
(pipeline.json), but only the attendance camera's results become check-ins (see emit.py).
Adapters only: the face detector is app/pipeline/detector.py (Mai Chi); the three models live in
ml/anti_spoofing/ (Hồng Minh), ml/face_recognition/ (Thuận Minh) and ml/emotion/ (Minh Thành), each as
infer.py plus <feature>.pt, found by app/core/ml_models.py.

Each face is cut out once per model with that model's margin (ml_models.MARGIN, the same crops as the Features demo):
face["crops"] = {"face_recognition": ..., "anti_spoofing": ..., "emotion": ...} (None when empty)."""
from collections import deque

from ...services.gallery import identify_face
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
    """liveness.check() wants ~10 recent crops of one face. Options: {"frames": 10, "max_missed": 5}.
    EVERY face in the frame is checked, not only the largest: a face shown on a phone screen is usually smaller
    than the person holding it, and a face that is never checked used to be recognised as if it were live.
    Each face keeps its own buffer of recent crops; a face is followed from frame to frame by box overlap
    (IoU), and a buffer is dropped after `max_missed` frames without a match.
    TODO: key the buffers by global ID once the matcher links faces to tracks."""
    MIN_IOU = 0.3

    def setup(self):
        self.liveness = load_infer("anti_spoofing")
        self.frames = int(self.options.get("frames", 10))
        self.max_missed = int(self.options.get("max_missed", 5))
        self.tracks = []        # [{"box", "recent": deque of crops, "missed": frames since last seen}]

    @staticmethod
    def _iou(a, b):
        ax, ay, aw, ah = a[:4]
        bx, by, bw, bh = b[:4]
        w = min(ax + aw, bx + bw) - max(ax, bx)
        h = min(ay + ah, by + bh) - max(ay, by)
        inter = max(0.0, w) * max(0.0, h)
        union = aw * ah + bw * bh - inter
        return inter / union if union > 0 else 0.0

    def process(self, ctx):
        for t in self.tracks:
            t["missed"] += 1
        free = list(self.tracks)
        for face in sorted(ctx.faces, key=lambda f: -f["box"][2] * f["box"][3]):
            crop = face["crops"]["anti_spoofing"]
            if crop is None:
                face["live"], face["liveness_score"] = False, 0.0    # no usable crop: never accept without evidence
                continue
            best = max(free, key=lambda t: self._iou(t["box"], face["box"]), default=None)
            if best is not None and self._iou(best["box"], face["box"]) >= self.MIN_IOU:
                free.remove(best)
                track = best
            else:
                track = {"recent": deque(maxlen=self.frames)}
                self.tracks.append(track)
            track.update(box=face["box"], missed=0)
            track["recent"].append(crop)
            result = self.liveness.check(list(track["recent"]))
            face["live"], face["liveness_score"] = bool(result["live"]), result.get("score")
        self.tracks = [t for t in self.tracks if t["missed"] <= self.max_missed]


@register_stage("recognize")
class Recognize(Stage):
    """Match against the complete gallery and its optional glasses-free view."""

    def setup(self):
        self.recognizer = load_infer("face_recognition")
        self.threshold = self.options.get("threshold")

    def process(self, ctx):
        profiles = self.shared.get("face_profiles", (self.shared.get("gallery", {}), None))
        for face in ctx.faces:
            crop = face["crops"]["face_recognition"]
            if face.get("live") is False or crop is None:
                continue                       # never identify a spoof
            student_id, score, cutoff = identify_face(self.recognizer, crop, profiles, self.threshold, face.get("glasses"))
            face.update(student_id=student_id, similarity=score, recognition_threshold=cutoff)


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
