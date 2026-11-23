"""The presence_verification feature plug-in (app/features/presence_verification/).

Run from backend/:   python -m unittest discover -s tests -t .
The route test needs the trained model (python ml/presence_verification/train.py) and is skipped without it.
"""
import os
import tempfile
import unittest

from app.core.events import EventBus
from app.core.features import load_features
from app.features import presence_verification as pv

MODEL = pv.REPO_DIR / "ml" / "presence_verification" / "presence_verification.joblib"


class _Engine:
    def __init__(self):
        self.bus, self.shared = EventBus(), {}


class MissingModel(unittest.TestCase):
    def test_fails_cleanly_without_the_model(self):
        old = os.environ.get("HAWKEYE_PRESENCE_VERIFICATION_WEIGHTS")
        os.environ["HAWKEYE_PRESENCE_VERIFICATION_WEIGHTS"] = os.path.join(tempfile.gettempdir(), "no_such.joblib")
        try:
            loaded, _ = load_features({"presence_verification": True}, _Engine())
        finally:
            if old is None:
                os.environ.pop("HAWKEYE_PRESENCE_VERIFICATION_WEIGHTS")
            else:
                os.environ["HAWKEYE_PRESENCE_VERIFICATION_WEIGHTS"] = old
        d = loaded["presence_verification"].describe()
        self.assertEqual(d["status"], "failed")
        self.assertIn("not found", d["error"])

    def test_disabled_by_default(self):
        loaded, _ = load_features({}, _Engine())
        self.assertEqual(loaded["presence_verification"].describe()["status"], "disabled")


@unittest.skipUnless(MODEL.is_file(), "presence_verification.joblib not trained yet")
class Route(unittest.TestCase):
    def test_take_route_shape(self):
        loaded, _ = load_features({"presence_verification": True}, _Engine())
        self.assertEqual(loaded["presence_verification"].status, "ready")
        r = pv.take_result(1)
        for k in ("take", "check_ins", "crossings", "matches", "alerts", "students", "trails", "model"):
            self.assertIn(k, r)
        self.assertEqual(r["alerts"], [])                         # take 1 is a normal take
        self.assertEqual(len(r["matches"]), 4)


if __name__ == "__main__":
    unittest.main()
