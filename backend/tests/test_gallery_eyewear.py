import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from app.services import gallery


class EyewearProfiles(unittest.TestCase):
    def setUp(self):
        self.infer = Mock()
        self.infer.matching_strategy.return_value = "centroid"
        self.infer.threshold.return_value = 0.6922
        self.infer.identify.return_value = ("A", 0.81)
        self.crop = object()
        self.full = {"A": [object(), object()]}
        self.bare = {"A": [self.full["A"][0]]}

    def test_same_identity_uses_both_gallery_views(self):
        profiles = (self.full, self.bare)
        self.assertEqual(gallery.identify_face(self.infer, self.crop, profiles, None, False), ("A", 0.81, None))
        self.infer.identify.assert_called_with(self.crop, self.bare, None)
        self.assertEqual(gallery.identify_face(self.infer, self.crop, profiles, None, True), ("A", 0.81, 0.74))
        self.infer.identify.assert_called_with(self.crop, self.full, 0.74)

    def test_recognition_falls_back_without_an_eyewear_label(self):
        with patch.object(gallery, "_eyewear", return_value=None):
            gallery.identify_face(self.infer, self.crop, (self.full, self.bare), None)
        self.infer.identify.assert_called_once_with(self.crop, self.full, None)

    def test_legacy_checkpoint_uses_general_gallery(self):
        self.infer.matching_strategy.return_value = "best_photo"
        gallery.identify_face(self.infer, self.crop, (self.full, self.bare), 0.5254, True)
        self.infer.identify.assert_called_once_with(self.crop, self.full, 0.5254)


class EyewearCache(unittest.TestCase):
    def test_original_cache_can_still_be_read(self):
        vector = np.arange(512, dtype=np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "face_embeddings.npz"
            np.savez(path, keys=json.dumps(["old"]), vectors=[vector], found=[True])
            with patch.object(gallery, "EMBEDDING_CACHE", path):
                restored, glasses = gallery._read_cache()["old"]
        np.testing.assert_array_equal(restored, vector)
        self.assertIsNone(glasses)

    def test_eyewear_labels_survive_cache_round_trip(self):
        vector = np.arange(512, dtype=np.float32)
        original = {"bare": (vector, False), "glasses": (vector, True), "no_face": None}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "face_embeddings.npz"
            with patch.object(gallery, "EMBEDDING_CACHE", path):
                gallery._write_cache(original)
                restored = gallery._read_cache()
        self.assertIs(restored["bare"][1], False)
        self.assertIs(restored["glasses"][1], True)
        self.assertIsNone(restored["no_face"])
