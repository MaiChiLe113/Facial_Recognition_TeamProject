"""The plug-in core that runs the per-frame pipeline.

  types.py     shared data shapes: FrameContext (one frame moving through the stages) and Event
  registry.py  @register_stage / @register_feature: add a part by name, no central list to edit
  events.py    EventBus: stages publish events (seen, check_in, spoof, in, out), features subscribe
  runner.py    CameraPipeline: runs the stage list of one camera and isolates failures
  engine.py    Engine: reads backend/pipeline.json, builds one pipeline per camera, loads features
  stages/      thin adapters that call the model files in app/pipeline/ (owned by teammates)
  features.py  Feature base class + loader for app/features/<name>/

Failure rules (so one part cannot break the others):
  - A stage or feature that fails to import, set up or run is marked and skipped; the rest keep running.
  - A stub that raises NotImplementedError is shown as "not_ready", not as an error.
  - If the engine cannot start at all, the HTTP API (dashboard, demo, tracks) still runs.
  - GET /api/pipeline/status shows the state of every stage, subscriber and feature.
"""
