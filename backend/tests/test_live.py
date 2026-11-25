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


class LiveDrawing(unittest.TestCase):
    def test_smoothing_settles_jitter_and_forgets_old_boxes(self):
        st = {}
        xs = [live._smooth(st, (100 + (4 if i % 2 else -4), 50, 40, 80), i * 0.1)[0] for i in range(12)]
        self.assertLess(max(xs[-4:]) - min(xs[-4:]), 8)          # raw boxes swing by 8 px
        self.assertEqual(live._smooth(st, (300, 50, 40, 80), 1.1 + live.HOLD_SECONDS + 1)[0], 300)

    @unittest.skipUnless(importlib.util.find_spec("cv2") and importlib.util.find_spec("numpy"), "needs opencv")
    def test_labels_of_stacked_boxes_do_not_overlap(self):
        import numpy as np
        img = np.zeros((360, 640, 3), np.uint8)
        drawn = []
        import cv2
        orig = cv2.rectangle
        cv2.rectangle = lambda im, a, b, c, t: drawn.append((a, b)) if t == -1 else None
        try:
            live._draw_labels(img, [(100, 100, 80, 160, f"ID {i}", (0, 255, 0), 0) for i in range(3)])
        finally:
            cv2.rectangle = orig
        rects = [(a[0], a[1], b[0] - a[0], b[1] - a[1]) for a, b in drawn]
        for i, r in enumerate(rects):
            for q in rects[i + 1:]:
                self.assertFalse(r[0] < q[0] + q[2] and q[0] < r[0] + r[2] and r[1] < q[1] + q[3] and q[1] < r[1] + r[3])


class DoorHandoff(unittest.TestCase):
    """The doorway's check-in names the corridor / classroom track standing at the door (live link_names.py)."""

    def setUp(self):
        live._checkins.clear()
        self.cam = live.LiveCamera("cam_1")

    def at(self, tid, zone, t):
        return live._door_crossing(self.cam, "outside", tid, zone, t)

    def checkin(self, t, sid="SWH02378", name="Le Mai Chi"):
        live._record_checkins([{"student_id": sid, "live": True}], {sid: name}, t)

    def test_the_one_person_at_the_door_gets_the_name_and_old_crossings_too(self):
        self.at(7, "corridor", 0.0)
        self.assertEqual(self.at(7, "door", 1.0), "entered the classroom")
        self.cam.door_seq += 1
        self.cam.door_events.append({"seq": 1, "t": 1.0, "id": 7, "action": "entered the classroom", "name": None})
        self.checkin(2.5)
        live._handoff(self.cam, 2.6)
        self.assertEqual(self.cam.people[7]["name"], "Le Mai Chi")
        self.assertEqual(live._door_text(self.cam.door_events[0])["event"], "Le Mai Chi (ID 7) entered the classroom")

    def test_two_people_at_the_door_get_no_name(self):
        self.at(7, "door", 1.0)
        self.at(8, "door", 1.2)
        self.checkin(2.0)
        live._handoff(self.cam, 2.1)
        self.assertFalse(self.cam.people[7].get("name") or self.cam.people[8].get("name"))

    def test_a_check_in_long_after_the_door_names_nobody(self):
        self.at(7, "door", 1.0)
        self.at(7, "corridor", 1.5)
        self.checkin(1.0 + live.HANDOFF_S + 2)
        live._handoff(self.cam, 1.0 + live.HANDOFF_S + 2.1)
        self.assertIsNone(self.cam.people[7].get("name"))

    def test_a_name_is_not_given_to_a_second_live_track(self):
        self.at(7, "door", 1.0)
        self.checkin(1.5)
        live._handoff(self.cam, 1.6)
        self.at(9, "door", 2.0)               # ID switch at the door while ID 7 is still seen
        self.cam.people[7]["t"] = 2.0
        live._handoff(self.cam, 2.1)
        self.assertIsNone(self.cam.people[9].get("name"))

    def test_spoofs_do_not_check_in(self):
        live._record_checkins([{"student_id": "SWH02378", "live": False}], {}, 1.0)
        self.assertEqual(len(live._checkins), 0)


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
