"""Attendance rules (design doc section 6).  Owner: Đức Mạnh + Mai Chi

1. New person on any camera -> new global ID, shown "ID n (unknown)".
2. Check-in at the attendance cam: liveness passes + face matches -> link ID to student.
   Liveness fails -> log "spoof attempt".
3. Checked-in track appears in CAM2 -> "in class", interval opens.
4. Track leaves CAM2 (grace period) or is seen on CAM1 -> "out", interval closes.
5. Return -> new interval. Total time = sum of intervals.
6. Attended = checked in AND at least one in-class interval (late / minimum-time rule TBC).
"""

GRACE_SECONDS = 10  # TODO: agree on the value


class AttendanceLog:
    def on_check_in(self, global_id, student_id, liveness_score, emotion, timestamp):
        raise NotImplementedError

    def on_seen(self, cam_id, global_id, timestamp):
        raise NotImplementedError

    def tick(self, timestamp):
        """Close intervals for people not seen in CAM2 for GRACE_SECONDS."""
        raise NotImplementedError
