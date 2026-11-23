"""SQLite layer: seeding from data/mock/ and the shapes the frontend reads. Uses a temporary database."""
import tempfile
import unittest
from pathlib import Path

from app.db import connect, init_db
from app.db import queries
from app.db.seed import reset


class DbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.sqlite3"
        self.assertTrue(init_db(self.db))

    def tearDown(self):
        from app.db import _engines
        _engines.pop(self.db).dispose()
        self.tmp.cleanup()

    def test_second_init_does_not_seed_again(self):
        self.assertFalse(init_db(self.db))

    def test_roster_courses_become_enrollments(self):
        chi = next(s for s in queries.list_students(self.db) if s["student_id_vn"] == "SWH02378")
        self.assertEqual(chi["courses"], [1, 2])
        self.assertEqual(chi["photo"], "/photos/SWH02378")

    def test_sessions_newest_first_with_events(self):
        sessions = queries.list_sessions(self.db)
        dates = [s["date"] + s["start"] for s in sessions]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertTrue(all(s["events"] for s in sessions))

    def test_dashboard_keeps_its_shape(self):
        d = queries.build_dashboard(self.db)
        for key in ["course", "session", "roster", "events", "attendance_cam_status", "map"]:
            self.assertIn(key, d)
        self.assertTrue(any(r["student_id"] == "SWH01234" for r in d["roster"]))   # Minh Thành, no longer a placeholder

    def test_manual_attendance_change_is_saved(self):
        sid = queries.list_sessions(self.db)[0]["id"]
        row = queries.update_attendance(sid, "SWH02486", {"attended": True, "status": "in_class"}, self.db)
        self.assertEqual((row["attended"], row["status"]), (True, "in_class"))
        again = next(a for a in queries.list_sessions(self.db)[0]["attendance"] if a["student_id_vn"] == "SWH02486")
        self.assertTrue(again["attended"])
        with self.assertRaises(ValueError):
            queries.update_attendance(sid, "SWH02486", {"status": "asleep"}, self.db)
        with self.assertRaises(LookupError):
            queries.update_attendance(9999, "SWH02486", {"status": "left"}, self.db)

    def test_reset_empties_tables(self):
        reset(self.db)
        with connect(self.db) as conn:
            self.assertEqual(conn.exec_driver_sql("SELECT COUNT(*) FROM students").scalar(), 0)


if __name__ == "__main__":
    unittest.main()
