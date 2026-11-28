"""live_face_scan (app/services/enrol.py, app/api/enrol.py) and registering from a scan (POST /api/students).
The face detector and the models are replaced by fakes: these tests check the session logic, not the models."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.db
from app.api import enrol as enrol_api
from app.api import records
from app.db import init_db
from app.services import enrol, gallery

W, H = 1920, 1080


def marks(yaw=0.0, pitch=0.0, cx=960, cy=500, eye=120):
    """Landmarks that head_pose() turns back into roughly (yaw, pitch)."""
    nose_dx = np.sin(np.radians(yaw)) * eye / 2.2
    face_h = 1.3 * eye
    nose_dy = (pitch / 120 + 0.55) * face_h
    ey = cy - face_h / 2
    return [(cx - eye / 2, ey), (cx + eye / 2, ey), (cx + nose_dx, ey + nose_dy),
            (cx - eye / 2.5, ey + face_h), (cx + eye / 2.5, ey + face_h)]


def face(yaw=0.0, pitch=0.0, size=300):
    return (810, 350, size, size, 0.95, marks(yaw, pitch))


def frame(grey=128):
    img = np.full((H, W, 3), grey, np.uint8)
    cv2.circle(img, (960, 500), 120, (grey // 2,) * 3, 6)        # some edges so nothing reads as empty
    return img


class Fakes:
    def __init__(self, test, quality=0.9, live=True):
        self.quality, self.live, self.faces = quality, live, [face()]
        infers = {"anti_spoofing": type("A", (), {"check": staticmethod(lambda crops: {"live": self.live, "score": 0.9 if self.live else 0.1})}),
                  "live_face_scan": type("Q", (), {"align_crop": staticmethod(lambda img, marks: img[:128, :128])}),
                  "glasses_detection": type("G", (), {"predict": staticmethod(lambda c: {"glasses": False, "glasses_score": 0.1})}),
                  "face_recognition": type("R", (), {"identify": staticmethod(lambda c, g, t: (None, 0.2)),
                                                     "threshold": staticmethod(lambda: 0.69)})}
        for p in (patch.object(enrol, "_infer", lambda f: infers[f]),
                  patch.object(enrol, "quality_model", lambda: (lambda c: self.quality, 0.5, "live_face_scan")),
                  patch("app.pipeline.detector.detect_faces_landmarks", lambda *a, **k: self.faces),
                  patch.object(gallery, "registered_faces", lambda: ({}, {})),
                  patch.object(enrol, "CALIB_FRAMES", 0),
                  patch.object(enrol, "FRAME_LOG", Path(tempfile.gettempdir()) / "enrol_frames_test.jsonl"),
                  patch.object(enrol, "DETECT_W", 10**6)):   # the fake detector answers in full-frame pixels
            p.start()
            test.addCleanup(p.stop)


class Pose(unittest.TestCase):
    def test_head_pose_round_trip(self):
        for yaw, pitch in ((0, 0), (25, 0), (-30, 0), (0, -20), (0, 20)):
            y, p = enrol.head_pose(marks(yaw, pitch))
            self.assertAlmostEqual(y, yaw, delta=3)
            self.assertAlmostEqual(p, pitch, delta=3)

    def test_slots(self):
        self.assertEqual(enrol.slot_for(0, 0), "front")
        self.assertEqual(enrol.slot_for(25, 0), "left")      # nose to the image right = person turned left
        self.assertEqual(enrol.slot_for(-25, 0), "right")
        self.assertIsNone(enrol.slot_for(0, -20))          # chin up / down: no slot
        self.assertIsNone(enrol.slot_for(0, 20))
        self.assertEqual(enrol.slot_for(13, 0), "left")      # no dead zone next to front
        self.assertIsNone(enrol.slot_for(25, -30))         # turned and chin up at once: no slot


class Analyse(unittest.TestCase):
    def setUp(self):
        self.f = Fakes(self)
        self.s = enrol.get(enrol.new_session())

    def test_keeps_best_three_different_views_per_slot(self):
        for q, yaw in ((0.6, -8), (0.9, 0), (0.7, 8), (0.95, -1), (0.55, 4)):
            self.f.quality, self.f.faces = q, [face(yaw)]
            enrol.analyse(self.s, frame(), final=True)
        kept = self.s["slots"]["front"]
        self.assertEqual([e["quality"] for e in kept], [0.95, 0.7, 0.6])     # 0.95 replaced the 0.9 at the same view
        self.assertTrue(all(abs(a["yaw"] - b["yaw"]) >= enrol.MIN_POSE_GAP for a in kept for b in kept if a is not b))
        self.assertNotIn("front", enrol.missing_slots(self.s))

    def test_preview_frames_are_not_kept(self):
        r = enrol.analyse(self.s, frame(), final=False)
        self.assertTrue(r["accepted"])
        self.assertFalse(r["kept"])
        self.assertEqual(self.s["slots"]["front"], [])

    def test_refusals(self):
        cases = [("several_faces", dict(faces=[face(), face(size=200)])), ("no_face", dict(faces=[])),
                 ("too_small", dict(faces=[face(size=60)])), ("low_quality", dict(quality=0.2)),
                 ("not_live", dict(live=False)), ("between_poses", dict(faces=[face(yaw=25, pitch=-30)]))]
        for reason, over in cases:
            with self.subTest(reason):
                s = enrol.get(enrol.new_session())
                f = Fakes(self, **{k: v for k, v in over.items() if k != "faces"})
                if "faces" in over:
                    f.faces = over["faces"]
                r = enrol.analyse(s, frame(), final=True)
                self.assertEqual(r["reason"], reason)
                self.assertFalse(r["kept"])
        self.assertEqual(enrol.analyse(enrol.get(enrol.new_session()), frame(20), final=True)["reason"], "too_dark")

    def test_hint_points_to_missing_slot(self):
        for yaw in (-7, 0, 7):
            self.f.faces = [face(yaw)]
            enrol.analyse(self.s, frame(), final=True)
        self.assertEqual(enrol.missing_slots(self.s)[0], "left")
        self.assertEqual(enrol.analyse(self.s, frame())["hint"], "left side: turn your head to your left a bit more")

    def test_calibrates_on_the_persons_own_straight_pose(self):
        with patch.object(enrol, "CALIB_FRAMES", 3):
            s = enrol.get(enrol.new_session())
            self.f.faces = [face(0, 12)]              # this face reads 12 deg "down" when looking straight
            for i in range(3):
                r = enrol.analyse(s, frame(), final=True)
                if i < 2:
                    self.assertEqual(r["reason"], "calibrating")
                    self.assertFalse(r["kept"])
            self.assertEqual(r["slot"], "front")
            self.assertTrue(r["kept"])
            self.f.faces = [face(0, 32)]              # 20 deg further down than this person's straight
            self.assertIsNone(enrol.analyse(s, frame())["slot"])

    def test_overshoot_says_turn_back_not_other_side(self):
        self.assertEqual(enrol._hint(["left"], 60, 0), "left side: a little less, turn back slightly")
        self.assertEqual(enrol._hint(["right"], -60, 0), "right side: a little less, turn back slightly")
        self.assertEqual(enrol._hint(["left"], 8, 0), "left side: turn your head to your left a bit more")
        self.assertEqual(enrol._hint(["right"], 20, 0), "right side: turn your head to your right")

    def test_after_a_kept_photo_the_hint_asks_for_a_slightly_different_angle(self):
        self.assertEqual(enrol._hint(["left"], 25, 0), "hold still")
        self.assertIn("photo 2 of 3", enrol._hint(["left"], 25, 0, have=1))
        self.assertIn("move your head slightly", enrol._hint(["front"], 0, 0, have=2))
        self.assertEqual(enrol._hint(["left"], 60, 0, have=1), "left side: a little less, turn back slightly")

    def test_remove_still_reopens_the_slot(self):
        self.f.faces = [face(0)]
        enrol.analyse(self.s, frame(), final=True)
        self.assertEqual(len(self.s["slots"]["front"]), 1)
        enrol.remove_still(self.s, "front", 0)
        self.assertEqual(self.s["slots"]["front"], [])
        self.assertIn("front", enrol.missing_slots(self.s))
        with self.assertRaises(IndexError):
            enrol.remove_still(self.s, "front", 0)

    def test_glasses_stop_the_scan(self):
        g = type("G", (), {"predict": staticmethod(lambda c: {"glasses": True, "glasses_score": 0.9}),
                           "_load": staticmethod(lambda: {"threshold": 0.5})})
        real = enrol._infer
        with patch.object(enrol, "_infer", lambda f: g if f == "glasses_detection" else real(f)):
            self.f.faces = [face(0)]
            r = enrol.analyse(self.s, frame(), final=True)
        self.assertEqual(r["reason"], "glasses")
        self.assertFalse(r["kept"])
        self.assertIn("take off your glasses", r["hint"])

    def test_a_different_person_is_refused(self):
        people = iter([np.array([1, 0], np.float32), np.array([0, 1], np.float32)])
        rec = type("R", (), {"embed": staticmethod(lambda c: next(people))})
        real = enrol._infer
        with patch.object(enrol, "_infer", lambda f: rec if f == "face_recognition" else real(f)):
            self.f.faces = [face(-7)]
            self.assertTrue(enrol.analyse(self.s, frame(), final=True)["kept"])
            self.f.faces = [face(7)]
            r = enrol.analyse(self.s, frame(), final=True)
        self.assertEqual(r["reason"], "other_person")
        self.assertFalse(r["kept"])
        self.assertEqual(len(self.s["slots"]["front"]), 1)

    def test_live_scan_follows_the_slot_order(self):
        self.f.faces = [face(-25, 0)]                 # "right" before straight is done: refused, hint stays on front
        r = enrol.analyse(self.s, frame(), final=True)
        self.assertEqual(r["reason"], "other_pose")
        self.assertFalse(r["kept"])
        self.assertEqual(self.s["slots"]["right"], [])

    def test_target_is_widened(self):
        self.assertEqual(enrol.slot_for(10, 0), "front")
        self.assertEqual(enrol.slot_for(10, 0, target="left"), "left")

    def test_fills_all_slots(self):
        poses = {"front": (0, 0), "left": (25, 0), "right": (-25, 0)}
        for yaw, pitch in poses.values():
            for d in (-5, 0, 5):
                self.f.faces = [face(yaw + d, pitch)]
                r = enrol.analyse(self.s, frame(), final=True)
        self.assertTrue(r["done"])
        self.assertEqual(r["hint"], "done")


class Api(unittest.TestCase):
    def setUp(self):
        Fakes(self)
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.db, self.photos_dir = tmp / "test.sqlite3", tmp / "photos"
        init_db(self.db)
        for p in (patch.object(app.db, "DB_PATH", self.db), patch.object(records, "PHOTOS_DIR", self.photos_dir),
                  patch.object(gallery, "roster_changed")):
            p.start()
            self.addCleanup(p.stop)
        api = FastAPI()
        api.include_router(records.router)
        api.include_router(enrol_api.router)
        self.client = TestClient(api)

    def jpeg(self):
        return cv2.imencode(".jpg", frame())[1].tobytes()

    def test_failed_scan_is_marked_and_logged(self):
        sid = self.client.post("/api/enrol/session").json()["session_id"]
        with patch.object(enrol, "FAIL_LOG", Path(self.tmp.name) / "logs" / "enrol_failures.jsonl"):
            r = self.client.post(f"/api/enrol/session/{sid}/fail",
                                 data={"reason": "no_face", "attempts": "3", "reasons": '{"no_face": 40}'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["failed"]["reason"], "no_face")
        self.assertEqual(r.json()["failed"]["attempts"], 3)
        line = json.loads((Path(self.tmp.name) / "logs" / "enrol_failures.jsonl").read_text(encoding="utf-8"))
        self.assertEqual((line["session_id"], line["reasons"]), (sid, {"no_face": 40}))

    def test_scan_log_is_saved_only_on_request(self):
        logs = Path(self.tmp.name) / "logs"
        with patch.object(enrol, "SCAN_LOG_DIR", logs):
            sid = self.client.post("/api/enrol/session").json()["session_id"]
            url = f"/api/enrol/session/{sid}/log"
            self.assertEqual(self.client.post(url).json(), {"log_file": None, "rows": 0})
            for _ in range(2):
                self.client.post("/api/enrol/frame", data={"session_id": sid},
                                 files={"image": ("f.jpg", self.jpeg(), "image/jpeg")})
            self.assertFalse(logs.exists())          # scanning alone writes no CSV
            for _ in range(2):                       # saving twice rewrites the same file
                r = self.client.post(url)
                self.assertEqual(r.json()["rows"], 2, r.text)
        files = list(logs.glob("live_face_scan_*.csv"))
        self.assertEqual([f"logs/{f.name}" for f in files], [r.json()["log_file"]])
        lines = files[0].read_text(encoding="utf-8-sig").splitlines()
        self.assertEqual(lines[0], ",".join(enrol.LOG_COLUMNS))
        self.assertEqual(len(lines), 3)

    def test_scan_then_register(self):
        sid = self.client.post("/api/enrol/session").json()["session_id"]
        r = self.client.post("/api/enrol/frame", data={"session_id": sid, "final": "true"},
                             files={"image": ("f.jpg", self.jpeg(), "image/jpeg")})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["kept"])
        self.assertEqual(self.client.get(f"/api/enrol/session/{sid}/still/front/0").headers["content-type"], "image/jpeg")
        r = self.client.post("/api/students", data={"name": "Tran Van A", "student_id_vn": "SWH09998",
                                                    "courses": "[]", "enrol_session": sid})
        self.assertEqual(r.status_code, 201, r.text)
        folder = self.photos_dir / "SWH09998"
        scan = json.loads((folder / "scan.json").read_text(encoding="utf-8"))
        self.assertEqual(scan["source"], "live")
        self.assertEqual([i["file"] for i in scan["images"]], ["photo_01.jpg"])
        self.assertTrue((folder / "photo_01.jpg").is_file())
        self.assertEqual(self.client.get(f"/api/enrol/session/{sid}").status_code, 404)   # used up

    def test_register_needs_photos_or_scan(self):
        r = self.client.post("/api/students", data={"name": "A", "student_id_vn": "SWH09997", "courses": "[]"})
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/api/students", data={"name": "A", "student_id_vn": "SWH09997", "courses": "[]",
                                                    "enrol_session": "nope"})
        self.assertEqual(r.status_code, 404)

    def test_video(self):
        sid = self.client.post("/api/enrol/session", data={"source": "video"}).json()["session_id"]
        path = Path(self.tmp.name) / "v.mp4"
        out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (W, H))
        for _ in range(30):
            out.write(frame())
        out.release()
        r = self.client.post("/api/enrol/video", data={"session_id": sid},
                             files={"video": ("v.mp4", path.read_bytes(), "video/mp4")})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["slots"]["front"]), 1)          # one view repeated -> one still
        self.assertEqual(body["source"], "video")
        self.assertIn("ok", body["frame_reasons"])
        self.assertIsNotNone(body["slots"]["front"][0]["t"])


if __name__ == "__main__":
    unittest.main()


class MaskDetection(unittest.TestCase):
    """ml/mask_detection on a drawn face: skin everywhere vs a blue mask over the nose, mouth and chin."""
    MARKS = [(80, 90), (120, 90), (100, 115), (85, 135), (115, 135)]

    def image(self, mask):
        import cv2
        img = np.full((200, 200, 3), (120, 150, 200), np.uint8)     # skin-like BGR
        cv2.ellipse(img, (100, 110), (55, 75), 0, 0, 360, (110, 145, 205), -1)
        if mask:
            cv2.rectangle(img, (55, 105), (145, 175), (200, 140, 60), -1)  # blue surgical mask
        return img

    def test_mask_is_detected_and_bare_face_is_not(self):
        from app.core.ml_models import load_infer
        m = load_infer("mask_detection")
        self.assertTrue(m.check(self.image(True), self.MARKS)["mask"])
        self.assertFalse(m.check(self.image(False), self.MARKS)["mask"])

    def test_face_at_the_border_gives_no_decision(self):
        from app.core.ml_models import load_infer
        r = load_infer("mask_detection").check(self.image(False), [(5, 2), (9, 2), (7, 4), (6, 6), (8, 6)])
        self.assertIsNone(r["mask"])
