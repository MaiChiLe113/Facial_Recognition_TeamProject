"""Built-in event subscribers: the attendance rules (app/pipeline/attendance.py, Đức Mạnh + Mai Chi).

While AttendanceLog is a stub its handlers raise NotImplementedError and show as not_ready.
TODO (attendance.py): publish "in" / "out" events back onto the bus when intervals open and close.
"""
import logging

log = logging.getLogger("hawkeye")


def attach_attendance(bus, shared):
    try:
        from ..pipeline.attendance import AttendanceLog
    except Exception as e:  # noqa: BLE001
        log.warning("Attendance rules not loaded: %s", e)
        return f"{type(e).__name__}: {e}"
    att = shared.setdefault("attendance", AttendanceLog())

    def on_check_in(ev):
        att.on_check_in(ev.global_id, ev.student_id, ev.data.get("liveness_score"), ev.data.get("emotion"), ev.t)

    def on_seen(ev):
        att.on_seen(ev.cam_id, ev.global_id, ev.t)

    bus.subscribe("check_in", on_check_in, owner="attendance")
    bus.subscribe("seen", on_seen, owner="attendance")
    return None
