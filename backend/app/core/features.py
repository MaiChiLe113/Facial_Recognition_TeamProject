"""Features: optional add-ons (the individual innovation features) that react to events.

A feature lives in app/features/<name>/ and never edits another module. It can:
  - subscribe to events in setup()            (e.g. send an alert on "spoof")
  - read shared objects via engine.shared      (e.g. the matcher's map positions)
  - offer HTTP routes with `router`            (mounted at /api/features/<name>/...)
  - report its state with status()             (shown in GET /api/pipeline/status)

It only runs when backend/pipeline.json has  "features": {"<name>": true}.
See app/features/README.md for a step-by-step guide.
"""
import logging

from .discovery import import_all
from .registry import feature_classes

log = logging.getLogger("hawkeye")


class Feature:
    name = ""          # set by @register_feature
    router = None      # optional fastapi.APIRouter

    def __init__(self, options, engine):
        self.options = options if isinstance(options, dict) else {}
        self.engine = engine
        self.status, self.error = "pending", None

    def setup(self, bus):
        """Subscribe to events here: bus.subscribe("check_in", self.on_check_in, owner=self.name)"""

    def info(self):
        """Extra state to show in the status page."""
        return {}

    def describe(self):
        try:
            info = self.info() if self.status == "ready" else {}
        except Exception as e:  # noqa: BLE001
            info = {"info_error": f"{type(e).__name__}: {e}"}
        return {"feature": self.name, "status": self.status, "error": self.error, "info": info}


class _Unloaded:
    """Stand-in for a feature that is switched off or could not be created."""
    router = None

    def __init__(self, name, status, error=None):
        self.name, self.status, self.error = name, status, error

    def describe(self):
        return {"feature": self.name, "status": self.status, "error": self.error, "info": {}}


def load_features(config, engine):
    """config: pipeline.json "features" -> {name: true | false | {options}}.
    Return ({name: feature}, {module: import_error})."""
    errors = import_all("app.features")
    loaded = {}
    classes = feature_classes()
    for name, cls in classes.items():
        setting = config.get(name, False)
        if setting is False:
            loaded[name] = _Unloaded(name, "disabled", "Switched off: set it to true in backend/pipeline.json")
            continue
        try:
            feature = cls(setting, engine)
            feature.setup(engine.bus)
            feature.status = "ready"
        except Exception as e:  # noqa: BLE001 - a broken feature must not stop the engine
            log.exception("Feature %s failed to set up", name)
            feature = _Unloaded(name, "failed", f"setup: {type(e).__name__}: {e}")
        loaded[name] = feature
    for name, setting in config.items():
        if name not in classes and setting is not False:
            loaded[name] = _Unloaded(name, "failed", "Enabled in pipeline.json but no feature with this name was found")
    return loaded, errors
