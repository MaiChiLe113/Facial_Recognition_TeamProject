"""Hand-made door scenarios for the manual test (TEST.md, step 4). Needs the trained model.

    .venv/Scripts/python ml/presence_verification/tests/manual_scenarios.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import infer  # noqa: E402

DOOR, ROOM, CORRIDOR = (0.31, 0.87), (0.6, 0.5), (0.15, 0.6)


def walk_in(track, t0, door_s=4.0, step=0.5):
    """A cam_2 track standing at the door for door_s seconds from t0, then in the room for 2 s."""
    n_door, n_room = int(door_s / step), int(2 / step)
    return [{"t": round(t0 + i * step, 2), "track_id": track, "cam_id": "cam_2", "x": x, "y": y}
            for i, (x, y) in enumerate([DOOR] * n_door + [ROOM] * n_room)]


def show(title, check_ins, points):
    r = infer.audit_door(check_ins, points)
    print(f"\n== {title}")
    print("   matches:", [(m["student_id"], m["track_id"], m["dt"]) for m in r["matches"]])
    print("   alerts: ", [(a["code"], a["t"], a["reason"]) for a in r["alerts"]] or "none")


if __name__ == "__main__":
    show("1. Normal: A and B check in, each walks in",
         [{"t": 10.0, "student_id": "A"}, {"t": 30.0, "student_id": "B"}],
         walk_in("cam_2:1", 9.5) + walk_in("cam_2:2", 29.5))
    show("2. Tailgating: A checks in, two people walk in together",
         [{"t": 10.0, "student_id": "A"}],
         walk_in("cam_2:1", 9.5) + walk_in("cam_2:2", 11.5))
    show("3. Nobody checks in, someone walks in", [], walk_in("cam_2:1", 5.0))
    show("4. A checks in and walks off down the corridor",
         [{"t": 10.0, "student_id": "A"}],
         [{"t": 9.5 + i * 0.5, "track_id": "cam_1:1", "cam_id": "cam_1", "x": CORRIDOR[0], "y": CORRIDOR[1]}
          for i in range(10)])
