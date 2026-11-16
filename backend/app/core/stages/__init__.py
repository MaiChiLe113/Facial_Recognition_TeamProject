"""Pipeline stages. Every module in this folder is imported at start (see core/discovery.py),
so a new stage is a new file with @register_stage("<name>") plus its name in backend/pipeline.json.

Built-in stages (adapters around the model files in app/pipeline/):
  people.py          detect_people, track, match           (Mai Chi's detector / tracker / matcher)
  attendance_cam.py  detect_faces, liveness, recognize, emotion
  emit.py            emit_events: turns the frame's results into seen / check_in / spoof events
"""
