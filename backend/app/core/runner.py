"""Runs one camera's stage list on each frame, and keeps a failing stage from stopping the rest.

Stage status:  pending (set up, no frame yet) · ready · not_ready (stub: NotImplementedError)
               · failed (import/setup error, unknown name, or MAX_ERRORS errors while running)
Skipped stages leave their fields empty, and later stages simply work with less.
"""
import logging
import time

from .registry import stage_classes
from .types import FrameContext

log = logging.getLogger("hawkeye")

MAX_ERRORS = 20


class StageSlot:
    def __init__(self, name, stage=None, status="pending", error=None):
        self.name, self.stage, self.status, self.error = name, stage, status, error
        self.frames, self.errors, self.last_ms = 0, 0, None

    @property
    def runnable(self):
        return self.stage is not None and self.status in ("pending", "ready")

    def describe(self):
        return {"stage": self.name, "status": self.status, "frames": self.frames, "errors": self.errors,
                "last_ms": self.last_ms, "error": self.error}


def _todo(e):
    return f"TODO: {e}" if str(e) else "TODO (not implemented yet)"


class CameraPipeline:
    def __init__(self, cam_id, role, stage_names, options, shared, bus):
        self.cam_id, self.role, self.bus = cam_id, role, bus
        self.frames = 0
        classes = stage_classes()
        self.slots = []
        for name in stage_names:
            cls = classes.get(name)
            if cls is None:
                self.slots.append(StageSlot(name, status="failed", error=f"Unknown stage '{name}' (not registered)"))
                continue
            slot = StageSlot(name)
            try:
                slot.stage = cls(cam_id, role, options.get(name, {}), shared)
                slot.stage.setup()
            except NotImplementedError as e:
                slot.status, slot.error = "not_ready", _todo(e)
            except Exception as e:  # noqa: BLE001 - e.g. missing model weights or library
                slot.status, slot.error = "failed", f"setup: {type(e).__name__}: {e}"
                log.exception("Stage %s on %s failed to set up", name, cam_id)
            self.slots.append(slot)

    def process(self, image, t):
        """Run every runnable stage on one frame, then publish the frame's events. Returns the context."""
        ctx = FrameContext(cam_id=self.cam_id, role=self.role, t=t, image=image)
        self.frames += 1
        for slot in self.slots:
            if not slot.runnable:
                continue
            start = time.perf_counter()
            try:
                slot.stage.process(ctx)
                slot.status = "ready"
            except NotImplementedError as e:
                slot.status, slot.error = "not_ready", _todo(e)
            except Exception as e:  # noqa: BLE001 - one broken stage must not stop the frame
                slot.errors += 1
                slot.error = f"{type(e).__name__}: {e}"
                log.exception("Stage %s on %s failed", slot.name, self.cam_id)
                if slot.errors >= MAX_ERRORS:
                    slot.status = "failed"
            finally:
                slot.frames += 1
                slot.last_ms = round((time.perf_counter() - start) * 1000, 2)
        for event in ctx.events:
            self.bus.publish(event)
        return ctx

    def describe(self):
        return {"cam_id": self.cam_id, "role": self.role, "frames": self.frames,
                "stages": [s.describe() for s in self.slots]}
