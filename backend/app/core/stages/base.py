"""Base class for a pipeline stage.

A stage is one step on one camera's frames (detect, track, check liveness, ...).
One instance is created per camera that lists it in backend/pipeline.json.

    @register_stage("my_step")
    class MyStep(Stage):
        def setup(self):            # once at start: load the model. May raise.
            from ...pipeline import my_module
            self.model = my_module
        def process(self, ctx):     # every frame: read ctx fields, write your own
            ctx.extras["my_step"] = self.model.run(ctx.image)

Rules:
  - Import model code inside setup(), not at the top of the file, so a missing library
    only disables this stage.
  - Raise NotImplementedError while the model is a stub; the stage shows as not_ready.
  - Write only your own fields. If you need a new one, use ctx.extras["<your stage name>"].
"""


class Stage:
    name = ""        # set by @register_stage

    def __init__(self, cam_id, role, options, shared):
        self.cam_id = cam_id
        self.role = role
        self.options = options or {}      # pipeline.json "options" -> "<stage name>"
        self.shared = shared              # dict shared by every camera (e.g. the one GlobalMatcher)

    def setup(self):
        pass

    def process(self, ctx):
        raise NotImplementedError
