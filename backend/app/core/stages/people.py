"""People on CAM1 / CAM2: detect -> track per camera -> one global ID across cameras.
Adapters only: the models are in app/pipeline/detector.py, tracker.py, matcher.py (owner: Mai Chi)."""
from ..registry import register_stage
from .base import Stage


@register_stage("detect_people")
class DetectPeople(Stage):
    def setup(self):
        from ...pipeline import detector
        self.detector = detector

    def process(self, ctx):
        ctx.people = list(self.detector.detect_people(ctx.image))


@register_stage("track")
class Track(Stage):
    def setup(self):
        from ...pipeline.tracker import CameraTracker
        self.tracker = CameraTracker(self.cam_id)      # one tracker per camera

    def process(self, ctx):
        ctx.tracks = list(self.tracker.update(ctx.people, ctx.t))


@register_stage("match")
class Match(Stage):
    def setup(self):
        from ...pipeline.matcher import GlobalMatcher
        # One matcher for all cameras, so global IDs are shared.
        self.matcher = self.shared.setdefault("matcher", GlobalMatcher())

    def process(self, ctx):
        ctx.tracks = list(self.matcher.assign(ctx.cam_id, ctx.tracks, ctx.t))
