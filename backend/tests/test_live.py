"""Live cameras: the name vote across frames (app/services/live.py) and the live tracker (app/pipeline/tracker.py)."""
import importlib.util
import unittest

from app.services import live

HAS_TRACKER = all(importlib.util.find_spec(m) for m in ("numpy", "ultralytics", "lap"))


def face(box, sid=None, live_=True):
    return {"box": box, "student_id": sid, "live": live_}


class NameVote(unittest.TestCase):
    def setUp(self):
        self.cam = live.LiveCamera("attendance_cam")

    def frame(self, t, *faces):
        faces = list(faces)
        live._vote_names(self.cam, faces, t)
        return faces

    def test_a_missed_frame_keeps_the_name(self):
        self.frame(0.0, face((100, 100, 80, 80), "A"))
        f, = self.frame(0.2, face((104, 102, 80, 80)))
        self.assertEqual((f["student_id"], f["held"]), ("A", True))

    def test_the_most_frequent_name_wins(self):
        self.frame(0.0, face((100, 100, 80, 80), "B"))
        self.frame(0.2, face((100, 100, 80, 80), "A"))
        self.frame(0.4, face((100, 100, 80, 80), "A"))
        self.frame(0.6, face((100, 100, 80, 80), "A"))
        f, = self.frame(0.8, face((100, 100, 80, 80), "B"))          # A 3, B 2
        self.assertEqual((f["student_id"], f["held"]), ("A", True))

    def test_spoof_never_gets_a_name(self):
        self.frame(0.0, face((100, 100, 80, 80), "A"))
        f, = self.frame(0.2, face((100, 100, 80, 80), None, live_=False))
        self.assertIsNone(f["student_id"])

    def test_a_new_face_elsewhere_or_later_starts_fresh(self):
        self.frame(0.0, face((100, 100, 80, 80), "A"))
        far, = self.frame(0.2, face((400, 100, 80, 80)))
        self.assertIsNone(far["student_id"])
        late, = self.frame(0.2 + live.HOLD_SECONDS + 0.5, face((100, 100, 80, 80)))
        self.assertIsNone(late["student_id"])

    def test_two_faces_keep_their_own_names(self):
        self.frame(0.0, face((100, 100, 80, 80), "A"), face((400, 100, 80, 80), "B"))
        a, b = self.frame(0.2, face((102, 100, 80, 80)), face((398, 100, 80, 80)))
        self.assertEqual((a["student_id"], b["student_id"]), ("A", "B"))


@unittest.skipUnless(HAS_TRACKER, "needs numpy, ultralytics and lap")
class LiveTracker(unittest.TestCase):
    def test_a_walking_person_keeps_one_id_and_a_lost_one_is_forgotten(self):
        from app.pipeline.tracker import CameraTracker
        tr = CameraTracker("cam_1")
        ids = set()
        for i in range(20):                                     # 10 fps, moving right 8 px a frame
            out = tr.update([(100 + 8 * i, 200, 60, 160, 0.9)], i / 10)
            ids.update(o["local_id"] for o in out)
        self.assertEqual(len(ids), 1)
        self.assertEqual(tr.tracker.max_frames_lost, round(tr.buffer_seconds * tr.fps))
        self.assertEqual(tr.update([], 2.1), [])

    def test_no_detections_gives_no_tracks(self):
        from app.pipeline.tracker import CameraTracker
        self.assertEqual(CameraTracker("cam_2").update([], 0.0), [])


if __name__ == "__main__":
    unittest.main()
