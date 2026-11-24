"""emit_events: turn what the earlier stages found on this frame into events for the bus.
Put it last in a camera's stage list. It works with whatever the earlier stages managed to fill."""
from ..registry import register_stage
from ..types import Event
from .base import Stage


@register_stage("emit_events")
class EmitEvents(Stage):
    def process(self, ctx):
        for tr in ctx.tracks:
            if tr.get("global_id") is not None:
                ctx.events.append(Event("seen", ctx.cam_id, ctx.t, global_id=tr["global_id"],
                                        data={"box": tr.get("box"), "map_xy": tr.get("map_xy")}))
        for face in ctx.faces:
            data = {k: face.get(k) for k in ("liveness_score", "similarity", "emotion")}
            if face.get("live") is False:
                ctx.events.append(Event("spoof", ctx.cam_id, ctx.t, global_id=face.get("global_id"), data=data))
            elif face.get("live") and face.get("student_id") and ctx.role == "attendance":
                # Only the doorway checks people in; corridor / classroom recognition is shown, not logged.
                ctx.events.append(Event("check_in", ctx.cam_id, ctx.t, global_id=face.get("global_id"),
                                        student_id=face["student_id"], data=data))
        # "in" / "out" come from the attendance rules (app/pipeline/attendance.py), not from one frame.
