"""The ml/<feature>/infer.py + <feature>.pt convention, and the recognition maths that needs no weights.

Run from backend/:  python -m unittest discover -s tests -t .
"""
import os
import unittest
from unittest.mock import patch

import numpy as np

from app.core import ml_models


class Convention(unittest.TestCase):
    def test_weights_are_found_as_feature_dot_pt_inside_ml_feature(self):
        for feature in ml_models.FEATURES:
            path = ml_models.weights_file(feature)
            self.assertEqual(path, ml_models.ML_DIR / feature / f"{feature}.pt")

    def test_env_override(self):
        with patch.dict(os.environ, {"HAWKEYE_EMOTION_WEIGHTS": "somewhere/else.pt"}):
            self.assertEqual(ml_models.weights_file("emotion").name, "else.pt")

    def test_unknown_feature(self):
        with self.assertRaises(KeyError):
            ml_models.weights_file("liveness")

    def test_every_feature_has_importable_infer_code_without_torch(self):
        for feature in ml_models.FEATURES:
            module = ml_models.load_infer(feature)
            self.assertIs(module, ml_models.load_infer(feature))
        self.assertTrue(callable(ml_models.load_infer("anti_spoofing").check))
        self.assertTrue(callable(ml_models.load_infer("face_recognition").identify))
        self.assertTrue(callable(ml_models.load_infer("emotion").predict))

    def test_no_runs_folder_outside_ml(self):
        self.assertFalse((ml_models.ML_DIR.parent / "runs").exists(), "weights belong in ml/<feature>/, not runs/")


class Identify(unittest.TestCase):
    """identify() with a patched embed(): cosine, best template per student, threshold, ties."""

    @classmethod
    def setUpClass(cls):
        cls.fr = ml_models.load_infer("face_recognition")
        cls.basis = np.zeros(512, np.float32)
        cls.basis[0] = 1
        cls.other = np.zeros(512, np.float32)
        cls.other[1] = 1

    def identify(self, gallery, threshold):
        with patch.object(self.fr, "embed", return_value=self.basis):
            return self.fr.identify(np.zeros((8, 8, 3), np.uint8), gallery, threshold)

    def test_empty_gallery_is_unknown_without_loading_the_model(self):
        with patch.object(self.fr, "embed", side_effect=AssertionError("must not run")):
            self.assertEqual(self.fr.identify(None, {}, None), (None, 0.0))

    def test_best_template_wins_and_threshold_decides(self):
        template = 0.8 * self.basis + 0.6 * self.other
        gallery = {"A": [self.other, 7 * template], "B": [-self.basis]}
        who, score = self.identify(gallery, 0.79)
        self.assertEqual(who, "A")
        self.assertAlmostEqual(score, 0.8, places=6)
        self.assertIsNone(self.identify(gallery, 0.81)[0])

    def test_tie_between_students_is_unknown(self):
        self.assertEqual(self.identify({"A": [self.basis], "B": [self.basis]}, 0.5), (None, 1.0))

    def test_bad_input_is_rejected(self):
        for gallery in (None, {"A": np.zeros(128)}, {"A": np.full(512, np.nan)}):
            with self.assertRaises(ValueError):
                self.identify(gallery, 0.5)
        with self.assertRaises(ValueError):
            self.identify({"A": [self.basis]}, 2.0)


class EnrolmentRoot(unittest.TestCase):
    """The registered faces are found on the mounted Drive or in a copy downloaded into the repo."""

    def test_prefers_the_configured_root_then_falls_back_to_the_repo_folder(self):
        import tempfile
        from pathlib import Path
        from app.services import features_demo as fd

        with tempfile.TemporaryDirectory() as drive, tempfile.TemporaryDirectory() as repo:
            (Path(repo) / "AppliedML").mkdir()
            with patch.object(fd, "DRIVE_ROOT", Path(drive)), patch.object(fd, "REPO_DIR", Path(repo)):
                self.assertEqual(fd._enrolment_root(), Path(repo))        # Drive root has no AppliedML/
                (Path(drive) / "AppliedML").mkdir()
                self.assertEqual(fd._enrolment_root(), Path(drive))       # now the configured root wins


class MissingWeights(unittest.TestCase):
    def test_a_feature_without_weights_fails_clearly(self):
        with patch.dict(os.environ, {"HAWKEYE_EMOTION_WEIGHTS": "does/not/exist.pt"}):
            emotion = ml_models.load_infer("emotion")
            emotion._state.clear()
            with self.assertRaises(FileNotFoundError):
                emotion.predict(np.zeros((48, 48, 3), np.uint8))


if __name__ == "__main__":
    unittest.main()
