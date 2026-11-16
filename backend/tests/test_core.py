"""Checks that one broken part cannot break the others.

Run from backend/:   python -m unittest discover -s tests -t .
"""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from app.core.discovery import import_all
from app.core.engine import Engine
from app.core.events import EventBus
from app.core.features import Feature
from app.core.registry import register_feature, register_stage
from app.core.runner import MAX_ERRORS, CameraPipeline
from app.core.stages.base import Stage
from app.core.types import Event


# ---- test-only stages and features (names start with test_ so they never clash) ----
@register_stage("test_crash")
class Crash(Stage):
    def process(self, ctx):
        raise RuntimeError("boom")


@register_stage("test_stub")
class Stub(Stage):
    def process(self, ctx):
        raise NotImplementedError("model not trained yet")


@register_stage("test_bad_setup")
class BadSetup(Stage):
    def setup(self):
        raise FileNotFoundError("weights.pt")


@register_stage("test_mark")
class Mark(Stage):
    def process(self, ctx):
        ctx.extras.setdefault("ran", []).append(self.options.get("label", "mark"))
        ctx.events.append(Event("seen", ctx.cam_id, ctx.t, global_id=1))


@register_feature("test_counter")
class Counter(Feature):
    def setup(self, bus):
        self.count = 0
        bus.subscribe("seen", self.on_seen, owner=self.name)

    def on_seen(self, ev):
        self.count += 1

    def info(self):
        return {"count": self.count}


@register_feature("test_broken_feature")
class BrokenFeature(Feature):
    def setup(self, bus):
        raise ValueError("bad config")


def pipeline(stages, options=None):
    return CameraPipeline("cam_x", "inside", stages, options or {}, {}, EventBus())


class StageIsolation(unittest.TestCase):
    def test_crashing_stage_does_not_stop_the_next_one(self):
        p = pipeline(["test_crash", "test_mark"])
        ctx = p.process(None, 0.0)
        self.assertEqual(ctx.extras["ran"], ["mark"])
        self.assertEqual(p.slots[0].errors, 1)
        self.assertEqual(p.slots[1].status, "ready")

    def test_crashing_stage_is_switched_off_after_max_errors(self):
        p = pipeline(["test_crash", "test_mark"])
        for i in range(MAX_ERRORS + 5):
            p.process(None, float(i))
        self.assertEqual(p.slots[0].status, "failed")
        self.assertEqual(p.slots[0].errors, MAX_ERRORS)
        self.assertEqual(p.slots[1].frames, MAX_ERRORS + 5)

    def test_stub_is_not_ready_not_an_error(self):
        p = pipeline(["test_stub", "test_mark"])
        p.process(None, 0.0)
        p.process(None, 1.0)
        self.assertEqual(p.slots[0].status, "not_ready")
        self.assertEqual(p.slots[0].errors, 0)
        self.assertEqual(p.slots[0].frames, 1)          # not called again
        self.assertIn("model not trained yet", p.slots[0].error)

    def test_setup_error_and_unknown_name_skip_only_that_stage(self):
        p = pipeline(["test_bad_setup", "no_such_stage", "test_mark"])
        ctx = p.process(None, 0.0)
        self.assertEqual([s.status for s in p.slots], ["failed", "failed", "ready"])
        self.assertIn("weights.pt", p.slots[0].error)
        self.assertIn("Unknown stage", p.slots[1].error)
        self.assertEqual(ctx.extras["ran"], ["mark"])

    def test_options_reach_the_stage(self):
        ctx = pipeline(["test_mark"], {"test_mark": {"label": "hi"}}).process(None, 0.0)
        self.assertEqual(ctx.extras["ran"], ["hi"])

    def test_duplicate_name_is_rejected(self):
        with self.assertRaises(ValueError):
            @register_stage("test_mark")
            class Other(Stage):
                pass


class EventBusIsolation(unittest.TestCase):
    def test_failing_handler_does_not_block_others(self):
        bus, got = EventBus(), []
        bus.subscribe("seen", lambda e: 1 / 0, owner="broken")
        bus.subscribe("seen", lambda e: (_ for _ in ()).throw(NotImplementedError()), owner="stub")
        bus.subscribe("*", got.append, owner="ok")
        for i in range(3):
            bus.publish(Event("seen", "cam_1", float(i)))
        self.assertEqual(len(got), 3)
        status = {s["owner"]: s for s in bus.status()["subscribers"]}
        self.assertEqual(status["broken"]["errors"], 3)
        self.assertEqual(status["stub"]["status"], "not_ready")
        self.assertEqual(status["stub"]["calls"], 1)


class EngineWithRealConfig(unittest.TestCase):
    """The real backend/pipeline.json with today's stub models: nothing may raise."""

    def test_every_camera_processes_a_frame(self):
        engine = Engine.load().start()
        self.assertEqual(engine.import_errors, {})
        for cam_id in engine.pipelines:
            engine.process_frame(cam_id, None, 0.0)
        status = engine.status()
        for cam in status["cameras"]:
            by_name = {s["stage"]: s for s in cam["stages"]}
            self.assertEqual(by_name["emit_events"]["status"], "ready", cam["cam_id"])
            for s in cam["stages"]:
                self.assertIn(s["status"], ("ready", "not_ready"), s)

    def test_unknown_camera_is_a_clear_error(self):
        with self.assertRaises(KeyError):
            Engine.load().start().process_frame("cam_9", None, 0.0)


class FeatureIsolation(unittest.TestCase):
    def config(self, features):
        return {"cameras": {"cam_x": "inside"}, "roles": {"inside": ["test_mark"]}, "features": features}

    def test_enabled_feature_receives_events(self):
        engine = Engine(self.config({"test_counter": True})).start()
        engine.process_frame("cam_x", None, 0.0)
        engine.process_frame("cam_x", None, 1.0)
        self.assertEqual(engine.features["test_counter"].describe()["info"], {"count": 2})

    def test_features_are_off_unless_enabled(self):
        engine = Engine(self.config({})).start()
        self.assertEqual(engine.features["test_counter"].status, "disabled")

    def test_broken_or_missing_feature_does_not_stop_the_engine(self):
        engine = Engine(self.config({"test_counter": True, "test_broken_feature": True, "nope": True})).start()
        engine.process_frame("cam_x", None, 0.0)
        self.assertEqual(engine.features["test_broken_feature"].status, "failed")
        self.assertEqual(engine.features["nope"].status, "failed")
        self.assertEqual(engine.features["test_counter"].status, "ready")


class Discovery(unittest.TestCase):
    def test_a_module_that_fails_to_import_is_reported_and_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "test_pkg_discovery"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            (pkg / "good.py").write_text("LOADED = True\n")
            (pkg / "bad.py").write_text(textwrap.dedent("import a_library_nobody_installed\n"))
            (pkg / "_private.py").write_text("raise RuntimeError('should be skipped')\n")
            sys.path.insert(0, tmp)
            try:
                errors = import_all("test_pkg_discovery")
                self.assertEqual(list(errors), ["test_pkg_discovery.bad"])
                self.assertTrue(sys.modules["test_pkg_discovery.good"].LOADED)
            finally:
                sys.path.remove(tmp)


if __name__ == "__main__":
    unittest.main()
