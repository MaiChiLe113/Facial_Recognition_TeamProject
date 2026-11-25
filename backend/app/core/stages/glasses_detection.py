"""Add the glasses result to the attendance camera's detected faces."""
from ..ml_models import load_infer, weights_status
from ..registry import register_stage
from .base import Stage


@register_stage("glasses_detection")
class GlassesDetection(Stage):
    def setup(self):
        if not weights_status("glasses_detection")["found"]:
            raise NotImplementedError("Train 01_train_glasses.ipynb to add glasses detection weights")
        self.model = load_infer("glasses_detection")

    def process(self, ctx):
        for face in ctx.faces:
            crop = face["crops"].get("face_recognition")   # same box margin as glasses detection
            if crop is not None:
                face.update(self.model.predict(crop))
