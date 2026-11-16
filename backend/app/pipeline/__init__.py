"""Per-frame pipeline. Each module is a stub with its owner and a TODO.

Flow per camera frame:
  CAM1 / CAM2:     detector.detect_people -> tracker.update -> matcher.assign_global_ids
  Attendance cam:  detector.detect_faces -> liveness.check -> recognizer.identify -> emotion.predict
  All:             attendance.on_event (check-in, enter, exit, totals)
"""
