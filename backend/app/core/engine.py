"""The engine: config + event bus + one CameraPipeline per camera + features.

    engine = Engine.load()          # reads backend/pipeline.json
    engine.start()
    engine.process_frame("cam_1", image, t)   # called by the camera WebSocket (step 5) or the demo runner
    engine.status()                 # what GET /api/pipeline/status returns
"""
import json
import logging

from ..config import BACKEND_DIR
from .discovery import import_all
from .events import EventBus
from .features import load_features
from .runner import CameraPipeline
from .subscribers import attach_attendance

log = logging.getLogger("hawkeye")

PIPELINE_CONFIG = BACKEND_DIR / "pipeline.json"


class Engine:
    def __init__(self, config):
        self.config = config
        self.bus = EventBus()
        self.shared = {}               # objects every camera shares: matcher, gallery, attendance log
        self.pipelines = {}
        self.features = {}
        self.import_errors = {}
        self.attendance_error = None

    @classmethod
    def load(cls, path=PIPELINE_CONFIG):
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def start(self):
        self.import_errors.update(import_all("app.core.stages"))
        roles = self.config.get("roles", {})
        options = self.config.get("options", {})
        for cam_id, role in self.config.get("cameras", {}).items():
            self.pipelines[cam_id] = CameraPipeline(cam_id, role, roles.get(role, []), options, self.shared, self.bus)
        self.attendance_error = attach_attendance(self.bus, self.shared)
        self.features, errors = load_features(self.config.get("features", {}), self)
        self.import_errors.update(errors)
        log.info("Hawkeye engine started: %d cameras, %d features", len(self.pipelines),
                 sum(f.status == "ready" for f in self.features.values()))
        return self

    def process_frame(self, cam_id, image, t):
        pipeline = self.pipelines.get(cam_id)
        if pipeline is None:
            raise KeyError(f"Unknown camera '{cam_id}'. Add it to backend/pipeline.json.")
        return pipeline.process(image, t)

    def status(self):
        return {
            "running": True,
            "cameras": [p.describe() for p in self.pipelines.values()],
            "events": self.bus.status(),
            "features": [f.describe() for f in self.features.values()],
            "attendance_error": self.attendance_error,
            "import_errors": self.import_errors,
        }
