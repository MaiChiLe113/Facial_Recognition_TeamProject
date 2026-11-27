"""Registering a student (POST /api/students, Add person page) on a temporary database and photo folder."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.db
from app.api import records
from app.db import init_db, queries
from app.services import gallery

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


def form(**over):
    data = {"name": "Tran Van A", "student_id_vn": "swh09999", "student_id_au": "105500001", "year": "K6",
            "courses": json.dumps([1])}
    data.update(over)
    return data


def photos(n=10, name="face.jpg"):
    return [("photos", (f"{i}_{name}", JPEG, "image/jpeg")) for i in range(n)]


class RegisterStudent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.db, self.photos_dir = tmp / "test.sqlite3", tmp / "photos"
        init_db(self.db)
        for p in (patch.object(app.db, "DB_PATH", self.db), patch.object(records, "PHOTOS_DIR", self.photos_dir),
                  patch.object(gallery, "roster_changed")):
            self.reload = p.start()
            self.addCleanup(p.stop)
        api = FastAPI()
        api.include_router(records.router)
        self.client = TestClient(api)

    def tearDown(self):
        app.db._engines.pop(self.db).dispose()
        self.tmp.cleanup()

    def test_registers_student_saves_photos_and_reloads_faces(self):
        r = self.client.post("/api/students", data=form(), files=photos())
        self.assertEqual(r.status_code, 201, r.text)
        st = r.json()
        self.assertEqual((st["student_id_vn"], st["name"], st["courses"]), ("SWH09999", "Tran Van A", [1]))
        self.assertEqual(st["photo_folder"], "data/photos/SWH09999")
        self.assertEqual(st["photo"], "/photos/SWH09999")
        self.assertEqual(len(list((self.photos_dir / "SWH09999").glob("photo_*.jpg"))), 10)
        self.assertTrue(any(s["student_id_vn"] == "SWH09999" for s in queries.list_students(self.db)))
        self.reload.assert_called_once_with()

    def test_existing_student_is_refused_and_keeps_no_photos(self):
        r = self.client.post("/api/students", data=form(student_id_vn="SWH02378"), files=photos())
        self.assertEqual(r.status_code, 409)
        self.assertFalse((self.photos_dir / "SWH02378").exists())

    def test_bad_input_is_refused(self):
        cases = [form(name="  "), form(student_id_vn="12345"), form(student_id_au="12"), form(courses="one")]
        for data in cases:
            self.assertEqual(self.client.post("/api/students", data=data, files=photos()).status_code, 422, data)
        self.assertEqual(self.client.post("/api/students", data=form(), files=photos(21)).status_code, 422)
        self.assertEqual(self.client.post("/api/students", data=form(), files=photos(name="x.pdf")).status_code, 422)

    def test_unknown_course_rolls_back_the_photos(self):
        r = self.client.post("/api/students", data=form(courses="[99]"), files=photos())
        self.assertEqual(r.status_code, 422)
        self.assertFalse((self.photos_dir / "SWH09999").exists())
        self.assertIsNone(queries.get_student("SWH09999", self.db))


if __name__ == "__main__":
    unittest.main()


class RemoveStudent(RegisterStudent):
    def test_removes_an_added_student_and_their_photos(self):
        self.client.post("/api/students", data=form(), files=photos())
        self.assertTrue(queries.get_student("SWH09999", self.db)["removable"])
        r = self.client.delete("/api/students/SWH09999")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(queries.get_student("SWH09999", self.db))
        self.assertFalse((self.photos_dir / "SWH09999").exists())

    def test_drive_student_cannot_be_removed(self):
        self.assertFalse(queries.get_student("SWH02378", self.db)["removable"])
        self.assertEqual(self.client.delete("/api/students/SWH02378").status_code, 403)
        self.assertIsNotNone(queries.get_student("SWH02378", self.db))

    def test_unknown_student_is_404(self):
        self.assertEqual(self.client.delete("/api/students/SWH00000").status_code, 404)


class FillMissingCards(unittest.TestCase):
    def test_null_card_is_filled_from_the_roster_and_set_cards_are_kept(self):
        from sqlalchemy import text
        from app.db import connect
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "t.sqlite3"
            init_db(db)
            with connect(db) as conn:
                conn.execute(text("UPDATE students SET student_card = NULL WHERE student_id_vn = 'SWH02486'"))
                conn.execute(text("UPDATE students SET student_card = 'keep.jpg' WHERE student_id_vn = 'SWH02378'"))
            init_db(db)
            self.assertEqual(queries.get_student("SWH02486", db)["student_card"], "AppliedML/student_card_image/HongMinh.jpg")
            self.assertEqual(queries.get_student("SWH02378", db)["student_card"], "keep.jpg")
            app.db._engines.pop(db).dispose()
