"""Per-frame pipeline modules that are not models. detector.py is implemented; tracker.py, matcher.py and
attendance.py are still stubs with their owner and a TODO.

The three basic models (anti_spoofing, face_recognition, emotion) live in the repo's ml/ folder as
ml/<feature>/infer.py + ml/<feature>/<feature>.pt; see app/core/ml_models.py.

Flow per camera frame:
  CAM1 / CAM2:     detector.detect_people -> tracker.update -> matcher.assign_global_ids
  Attendance cam:  detector.detect_faces -> anti_spoofing.check -> face_recognition.identify -> emotion.predict
  All:             attendance.on_event (check-in, enter, exit, totals)
"""
