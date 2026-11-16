"""Example feature: counts events by type and offers them at GET /api/features/event_counter/.

Copy this folder to start your own feature (see app/features/README.md).
"""
from collections import Counter

from fastapi import APIRouter

from ...core.features import Feature
from ...core.registry import register_feature

router = APIRouter()
_current = None          # the running instance, so the route can read it


@register_feature("event_counter")
class EventCounter(Feature):
    router = router

    def setup(self, bus):
        global _current
        self.counts = Counter()
        self.last = None
        bus.subscribe("*", self.on_event, owner=self.name)      # "*" = every event type
        _current = self

    def on_event(self, ev):
        self.counts[ev.type] += 1
        self.last = {"type": ev.type, "cam_id": ev.cam_id, "t": ev.t, "global_id": ev.global_id}

    def info(self):
        return {"counts": dict(self.counts), "last": self.last}


@router.get("/")
def counts():
    return _current.info() if _current else {"counts": {}, "last": None}
