"""Unit tests for ml/presence_verification.  Run from the repo root:

    .venv/Scripts/python -m unittest discover -s ml/presence_verification/tests -v

Everything except InferContract runs without the trained model file.
"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from door_audit import (DtModel, assign, audit, detect_crossings, merge_check_ins,  # noqa: E402
                        trajectories_from_points)
from presence import apply_rules, student_rows  # noqa: E402
from pv_common import DATA, MODEL_FILE, load_ground_truth  # noqa: E402
from simulate import simulate  # noqa: E402
from trajectories import take_trajectories, to_map, zone_of  # noqa: E402


def traj(cam, zones_xy, t0=0.0, step=0.5, tid=1):
    pts = [{"t": t0 + i * step, "x": x, "y": y, "zone": zone_of(x, y)} for i, (x, y) in enumerate(zones_xy)]
    return {"cam_id": cam, "track_id": tid, "points": pts}


DOOR, ROOM, CORR = (0.31, 0.87), (0.6, 0.5), (0.15, 0.6)


class MapProjection(unittest.TestCase):
    def test_homography_reference_points(self):
        cal = json.loads((DATA / "calibration" / "cam_2_homography.json").read_text())
        w, h = cal["frame_size"]
        for (u, v), (mx, my) in zip(cal["image_points"], cal["map_points"]):
            box = [u / w - 0.01, v / h - 0.2, 0.02, 0.2]          # feet exactly at (u, v)
            p = to_map("cam_2", box)
            if p is None:                                          # outside cam_2's valid area or feet cut
                continue
            self.assertAlmostEqual(p[0], mx, places=2)
            self.assertAlmostEqual(p[1], my, places=2)

    def test_cut_feet_and_unknown_camera(self):
        self.assertIsNone(to_map("cam_2", [0.4, 0.5, 0.1, 0.5]))        # box touches the bottom edge
        self.assertIsNone(to_map("attendance_cam", [0.4, 0.3, 0.1, 0.3]))

    def test_zones(self):
        self.assertEqual(zone_of(*CORR), "corridor")
        self.assertEqual(zone_of(*DOOR), "door")
        self.assertEqual(zone_of(*ROOM), "room")


class Crossings(unittest.TestCase):
    def test_entry_and_exit(self):
        t_in = traj("cam_2", [DOOR] * 5 + [ROOM] * 5, tid=1)
        t_out = traj("cam_2", [ROOM] * 5 + [DOOR] * 5, t0=20, tid=2)
        c = detect_crossings([t_in, t_out])
        self.assertEqual([(x["direction"], x["t"]) for x in c], [("in", 2.0), ("out", 24.5)])
        self.assertEqual(c[0]["door"], [0.0, 2.0])

    def test_walking_past_the_door_inside_is_not_a_crossing(self):
        self.assertEqual(detect_crossings([traj("cam_2", [ROOM] * 4 + [DOOR] * 4 + [ROOM] * 4)]), [])

    def test_points_round_trip(self):
        pts = [{"t": i * 0.5, "track_id": "cam_2:7", "cam_id": "cam_2", "x": x, "y": y}
               for i, (x, y) in enumerate([DOOR] * 5 + [ROOM] * 3)]
        c = detect_crossings(trajectories_from_points(pts))
        self.assertEqual((len(c), c[0]["track_id"]), (1, "cam_2:7"))


class Matching(unittest.TestCase):
    dt = DtModel.fit([3.0, 4.0, 4.5, 3.5, 10.0, 12.0])

    def entry(self, t, i, door=None):
        return {"id": f"x{i}", "t": t, "track_id": f"cam_2:{i}", "direction": "in", "confidence": 1.0,
                "door": door or [t - 4, t], "corroborated": True}

    def test_dt_model(self):
        self.assertTrue(2.0 < self.dt.median() < 9.0)
        self.assertEqual(float(self.dt.logpdf(np.array([500.0]))[0]), -np.inf)
        self.assertGreater(self.dt.logpdf(np.array([5.0]))[0], self.dt.logpdf(np.array([40.0]))[0])

    def test_assign_leaves_bad_pairs_unmatched(self):
        cost = np.array([[1.0, 9.0], [9.0, 9.0]])
        self.assertEqual(assign(cost, unmatched_cost=3.0), [(0, 0)])

    def test_normal_no_alerts(self):
        r = audit([{"t": 10.0, "student_id": "A"}, {"t": 30.0, "student_id": "B"}],
                  [self.entry(14.0, 0), self.entry(34.5, 1)], self.dt)
        self.assertEqual(r["alerts"], [])
        self.assertEqual({(m["student_id"], m["crossing_id"]) for m in r["matches"]}, {("A", "x0"), ("B", "x1")})

    def test_tailgating_d2(self):
        r = audit([{"t": 10.0, "student_id": "A"}], [self.entry(14.0, 0), self.entry(15.5, 1)], self.dt)
        self.assertEqual([a["code"] for a in r["alerts"]], ["D2"])
        self.assertEqual(r["alerts"][0]["student_id"], "A")

    def test_no_checkin_d1_and_no_entry_d3(self):
        self.assertEqual([a["code"] for a in audit([], [self.entry(5.0, 0)], self.dt)["alerts"]], ["D1"])
        self.assertEqual([a["code"] for a in audit([{"t": 1.0, "student_id": "A"}], [], self.dt)["alerts"]], ["D3"])

    def test_duplicate_check_ins_merge(self):
        m = merge_check_ins([{"t": 11.3, "student_id": "A"}, {"t": 23.1, "student_id": "A"},
                             {"t": 90.0, "student_id": "A"}])
        self.assertEqual([(c["t"], c["merged"]) for c in m], [(11.3, 2), (90.0, 1)])


class Rules(unittest.TestCase):
    def session(self, crossings, check_ins, D=100.0):
        return {"duration": D, "check_ins": check_ins, "crossings": crossings, "points": []}

    def test_short_stay_and_early_leave(self):
        cr = [{"id": "x0", "t": 5.0, "track_id": "T", "direction": "in"},
              {"id": "x1", "t": 20.0, "track_id": "T", "direction": "out"}]
        door = {"check_ins": [{"t": 1.0, "student_id": "A", "merged": 1}], "alerts": [],
                "matches": [{"student_id": "A", "check_in_t": 1.0, "crossing_id": "x0", "track_id": "T",
                             "crossing_t": 5.0, "dt": 4.0, "cost": 1.0}]}
        row = student_rows(self.session(cr, [{"t": 1.0, "student_id": "A"}]), door)[0]
        self.assertEqual(set(row["rules"]), {"R2", "R5"})
        self.assertAlmostEqual(row["features"]["time_in_room_ratio"], 15 / 95, places=3)

    def test_never_entered_and_double_check_in(self):
        rules, _ = apply_rules("A", {"time_in_room_ratio": 0, "left_early_ratio": 0, "n_name_conflicts": 0,
                                     "max_speed": 0, "n_checkins": 1, "n_exits": 0}, True, 1.0)
        self.assertEqual(rules, ["R1"])
        rules, _ = apply_rules("A", {"time_in_room_ratio": 1, "left_early_ratio": 0, "n_name_conflicts": 0,
                                     "max_speed": 0, "n_checkins": 2, "n_exits": 0}, False, 1.0)
        self.assertEqual(rules, ["R4"])


class Simulation(unittest.TestCase):
    def test_reproducible_and_labelled(self):
        a, b = simulate(3, 5), simulate(3, 5)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        s = a[0]
        self.assertTrue(s["truth"]["students"])
        ids = {c["id"] for c in s["crossings"]}
        self.assertTrue(all(c in ids for _, c in s["truth"]["pairs"]))


class RecordedTakes(unittest.TestCase):
    def test_take1_entries_match_ground_truth(self):
        gt = sorted(r["appear_s"] for r in load_ground_truth(1) if r["event"] == "enter_class")
        entries = sorted(c["t"] for c in detect_crossings(take_trajectories(1)) if c["direction"] == "in")
        self.assertEqual(len(entries), len(gt))
        self.assertTrue(all(abs(e - g) <= 2.5 for e, g in zip(entries, gt)), (entries, gt))


@unittest.skipUnless(MODEL_FILE.is_file(), "presence_verification.joblib not trained yet")
class InferContract(unittest.TestCase):
    def test_analyze_take_shape(self):
        import infer
        r = infer.analyze_take(1)
        for k in ("take", "duration", "scored_as_class_s", "check_ins", "crossings", "matches", "alerts", "students",
                  "trails", "model"):
            self.assertIn(k, r)
        for s in r["students"]:
            self.assertTrue({"student_id", "score", "flagged", "reasons", "rules", "features"} <= set(s))
        json.dumps(r)                                   # must be JSON-serialisable for the API

    def test_take1_is_all_normal(self):
        import infer
        r = infer.analyze_take(1)
        self.assertEqual(r["alerts"], [])
        self.assertEqual([s["student_id"] for s in r["students"] if s["flagged"]], [])

    def test_audit_door_from_points(self):
        import infer
        pts = [{"t": i * 0.5, "track_id": "cam_2:1", "cam_id": "cam_2", "x": x, "y": y}
               for i, (x, y) in enumerate([DOOR] * 8 + [ROOM] * 4)]
        r = infer.audit_door([{"t": 1.0, "student_id": "A"}], pts)
        self.assertEqual((len(r["matches"]), r["alerts"]), (1, []))


if __name__ == "__main__":
    unittest.main()
