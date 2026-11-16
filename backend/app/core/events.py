"""Event bus: stages publish, anyone subscribes.

    bus.subscribe("check_in", handler, owner="event_counter")
    bus.subscribe("*", handler, owner="...")      # every event

A handler that raises is logged and counted; the other handlers still get the event.
A handler that raises NotImplementedError (a stub) is marked not_ready and not called again.
After MAX_ERRORS other failures it is marked failed and not called again.
"""
import logging
import threading
from collections import defaultdict

log = logging.getLogger("hawkeye")

MAX_ERRORS = 20


class _Subscription:
    def __init__(self, event_type, handler, owner):
        self.event_type, self.handler, self.owner = event_type, handler, owner
        self.status, self.error, self.calls, self.errors = "ready", None, 0, 0

    @property
    def active(self):
        return self.status == "ready"

    def describe(self):
        name = getattr(self.handler, "__qualname__", repr(self.handler))
        return {"owner": self.owner, "event": self.event_type, "handler": name, "status": self.status,
                "calls": self.calls, "errors": self.errors, "error": self.error}


class EventBus:
    def __init__(self):
        self._subs = defaultdict(list)
        self._lock = threading.Lock()
        self.published = defaultdict(int)

    def subscribe(self, event_type, handler, owner="unknown"):
        with self._lock:
            self._subs[event_type].append(_Subscription(event_type, handler, owner))

    def publish(self, event):
        with self._lock:
            self.published[event.type] += 1
            subs = [s for s in self._subs[event.type] + self._subs["*"] if s.active]
        for sub in subs:
            sub.calls += 1
            try:
                sub.handler(event)
            except NotImplementedError as e:
                sub.status, sub.error = "not_ready", f"TODO: {e}" if str(e) else "TODO (not implemented yet)"
            except Exception as e:  # noqa: BLE001 - a broken subscriber must not stop the others
                sub.errors += 1
                sub.error = f"{type(e).__name__}: {e}"
                log.exception("Event handler %s (%s) failed on %s", sub.describe()["handler"], sub.owner, event.type)
                if sub.errors >= MAX_ERRORS:
                    sub.status = "failed"

    def status(self):
        with self._lock:
            subs = [s.describe() for lst in self._subs.values() for s in lst]
        return {"published": dict(self.published), "subscribers": subs}
