"""AI face scan (app/services/enrol.py, app/api/enrol.py) and registering from a scan (POST /api/students).
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
                  "glasses_detection": type("G", (), {"predict": staticmethod(lambda c: {"glasses": False, "glasses_score": 0.1})}),
                  "face_recognition": type("R", (), {"identify": staticmethod(lambda c, g, t: (None, 0.2)),
                                                     "threshold": staticmethod(lambda: 0.69)})}
        for p in (patch.object(enrol, "_infer", lambda f: infers[f]),
                  patch.object(enrol, "quality_model", lambda: (lambda c: self.quality, 0.5, "face_quality")),
                  patch("app.pipeline.detector.detect_faces_landmarks", lambda *a, **k: self.faces),
                  patch.object(gallery, "registered_faces", lambda: ({}, {}))):
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
        self.assertEqual(enrol.slot_for(0, -20), "up")
        self.assertEqual(enrol.slot_for(0, 20), "down")
        self.assertIsNone(enrol.slot_for(12, 0))           # between front and right


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
                 ("not_live", dict(live=False)), ("between_poses", dict(faces=[face(yaw=12)]))]
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

    def test_overshoot_says_turn_back_not_other_side(self):
        self.assertEqual(enrol._hint(["left"], 60, 0), "left side: a little less, turn back slightly")
        self.assertEqual(enrol._hint(["right"], -60, 0), "right side: a little less, turn back slightly")
        self.assertEqual(enrol._hint(["left"], 8, 0), "left side: turn your head to your left a bit more")
        self.assertEqual(enrol._hint(["right"], 20, 0), "right side: turn your head to your right")
        self.assertEqual(enrol._hint(["up"], 0, -50), "chin up: a little less")
        self.assertEqual(enrol._hint(["down"], 0, 0), "chin down: tilt your chin down")

    def test_fills_all_slots(self):
        poses = {"front": (0, 0), "left": (25, 0), "right": (-25, 0), "up": (0, -20), "down": (0, 20)}
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
