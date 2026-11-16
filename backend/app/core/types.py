"""Data shapes shared by every stage and feature. Add fields; do not rename or remove them."""
from dataclasses import dataclass, field
from typing import Any

# Same values as events.type in app/db/schema.sql.
EVENT_TYPES = ("seen", "check_in", "spoof", "in", "out")


@dataclass
class Event:
    type: str                         # one of EVENT_TYPES (features may add their own, e.g. "alert")
    cam_id: str
    t: float                          # seconds: video time in demo mode, Unix time in live mode
    global_id: int | None = None
    student_id: str | None = None     # student_id_vn; None while unknown
    data: dict = field(default_factory=dict)   # extra values, e.g. {"liveness_score": 0.97, "emotion": "happy"}


@dataclass
class FrameContext:
    """One camera frame on its way through the stages. Each stage reads earlier fields and fills its own."""
    cam_id: str
    role: str                         # outside / inside / attendance (cameras.role in schema.sql)
    t: float
    image: Any                        # H x W x 3 BGR array (OpenCV convention)

    # detect_people: [(x, y, w, h, score), ...] in pixels
    people: list = field(default_factory=list)
    # track: [{"local_id", "box"}]; after match: [{"global_id", "box", "map_xy"}]
    tracks: list = field(default_factory=list)
    # detect_faces: [{"box", "score", "crop"}]; later stages add "live", "liveness_score",
    # "student_id", "similarity", "emotion", "emotion_score"
    faces: list = field(default_factory=list)
    # events to publish once every stage has run
    events: list = field(default_factory=list)
    # free space for added stages: extras["<stage or feature name>"] = anything
    extras: dict = field(default_factory=dict)
