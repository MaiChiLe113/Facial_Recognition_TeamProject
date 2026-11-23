"""app/pipeline/detector.py: detect_people (YOLO11n) and detect_faces (YuNet) on committed frames.

Run from backend/:  python -m unittest discover -s tests -t .
Skipped when OpenCV / Ultralytics or a model file is missing (see the detector's docstring).
"""
import importlib.util
import unittest

from app.config import REPO_DIR
from app.pipeline import detector

HAS_CV2 = importlib.util.find_spec("cv2") is not None
HAS_YOLO = importlib.util.find_spec("ultralytics") is not None
CALIBRATION = REPO_DIR / "data" / "calibration"


def frame(name):
    import cv2
    return cv2.imread(str(CALIBRATION / f"{name}_frame.png"))


def contains(box, x, y):
    bx, by, bw, bh = box[:4]
    return bx <= x <= bx + bw and by <= y <= by + bh


class Clip(unittest.TestCase):
    def test_box_is_clipped_to_the_frame(self):
        self.assertEqual(detector._clip(-10, 5, 50, 20, 30, 100), (0.0, 5.0, 30.0, 20.0))
        self.assertEqual(detector._clip(90, 90, 50, 50, 100, 100), (90.0, 90.0, 10.0, 10.0))


@unittest.skipUnless(HAS_CV2 and detector.FACE_WEIGHTS.is_file(), "needs opencv and the YuNet model")
class Faces(unittest.TestCase):
    def test_empty_doorway_has_no_face(self):
        self.assertEqual(detector.detect_faces(frame("attendance_cam")), [])

    def test_no_frame_gives_no_face(self):
        self.assertEqual(detector.detect_faces(None), [])

    def test_face_behind_the_corridor_glass(self):
        f = frame("cam_1")
        faces = detector.detect_faces(f)
        self.assertEqual(len(faces), 1)
        x, y, w, h, score = faces[0]
        self.assertTrue(contains(faces[0], 440, 335))       # the seated student's face
        self.assertTrue(0 < score <= 1 and w > 0 and h > 0)
        self.assertLessEqual(x + w, f.shape[1])
        self.assertLessEqual(y + h, f.shape[0])

    def test_faces_are_largest_first(self):
        import numpy as np
        f = frame("cam_1")
        big = np.concatenate([f, f], axis=1)                 # same face twice, side by side
        sizes = [w * h for _, _, w, h, _ in detector.detect_faces(big)]
        self.assertEqual(sizes, sorted(sizes, reverse=True))


@unittest.skipUnless(HAS_CV2 and HAS_YOLO, "needs opencv and ultralytics")
class People(unittest.TestCase):
    def test_empty_doorway_has_no_person(self):
        self.assertEqual(detector.detect_people(frame("attendance_cam")), [])

    def test_one_person_behind_the_corridor_glass(self):
        people = detector.detect_people(frame("cam_1"))
        self.assertEqual(len(people), 1)
        self.assertTrue(contains(people[0], 430, 370))
        self.assertGreaterEqual(people[0][4], detector.PERSON_CONF)


if __name__ == "__main__":
    unittest.main()
