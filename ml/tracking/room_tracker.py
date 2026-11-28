"""Keep names on people after their camera track breaks (room occupancy).  Owner: Mai Chi

The door handoff (link_names.py) names only the cam_1 / cam_2 track that stands at the door at check-in. When that
track ends (a person walks behind someone, sits down behind a desk, or the tracker switches IDs) the person goes on
under a new, unnamed track, and the roster shows them as "Left" although they are still in class.

Floor-map positions cannot follow them there: seated people's feet are hidden by the desks (cam_2) or by the wall
under the corridor window (cam_1 sees the room through the glass), so those boxes have no map position at all
(take 1: 0 of 119 / 116 keyframes for the two seated cam_2 tracks). What the map does give reliably is who is in the
room: everyone enters through the door and is named at check-in. So each camera view keeps the set of occupants and
which of them it can currently see:

  * occupant      a person named at check-in (attendance camera), in the room from their check-in time until a named
                  cam_2 track of theirs ends in the door zone (they left)
  * lost          an occupant this view saw on a named track that has ended, or never saw yet; unnamed tracks
                  longer than MIN_UNKNOWN_S that ended in the room are lost *unknown* people (not checked in)
  * new track     a track that starts inside the room (not at the door): it must be someone already there

A new track takes a name when (1) its first box is where a lost person's last box was on this camera
(seated people stay put: centre within SAME_SPOT box widths) and that person is named, or (2) no position matches
and exactly one lost person exists and is named. Otherwise (a lost unknown person could explain it too, or several
named people are lost) it stays Unknown. Names are written like the door handoff's (name, name_from,
name_source), so the roster, event log and map pick them up unchanged.

Called by link_names.link_take after the door handoff.
"""
import numpy as np

SAME_SPOT = 0.75          # box widths between a lost person's last box centre and a new track's first box centre
MAX_GAP_S = 15.0          # a lost person is a candidate for this long after their last box on this view
MIN_UNKNOWN_S = 2.0       # unnamed tracks shorter than this are fragments, not a separate unknown person
GLASS_BOTTOM = 0.7        # cam_1 boxes ending above this (fraction of the frame) are people seen through the glass


def _centre(box):
    return box[0] + box[2] / 2, box[1] + box[3] / 2


def _near(a, b):
    """True when box b's centre is within SAME_SPOT widths (of the wider box) of box a's centre."""
    (ax, ay), (bx, by) = _centre(a), _centre(b)
    w = max(a[2], b[2])
    return abs(ax - bx) <= SAME_SPOT * w and abs(ay - by) <= SAME_SPOT * max(a[3], b[3])


def _views(cam, tracks):
    """The tracks of one camera that show people inside the room: cam_2 = all its tracks; cam_1 = the ones seen
    through the glass (boxes cut off at the window sill)."""
    if cam == "cam_2":
        return list(tracks)
    return [tr for tr in tracks if np.median([k["box"][1] + k["box"][3] for k in tr["keyframes"]]) < GLASS_BOTTOM]


def carry_names(take, checkins, data, at_door):
    """checkins: {name: check-in time}. data: {"cam_1": [...tracks], "cam_2": [...tracks]} (names from the door
    handoff already set). at_door(cam, keyframes) -> True when those keyframes are in the door zone.
    Names tracks in place; returns report lines."""
    left_at = {}                                   # a named cam_2 track that ends at the door = left the room
    for tr in data["cam_2"]:
        n = tr.get("name")
        if n and at_door("cam_2", tr["keyframes"][-3:]) and tr["keyframes"][-1]["t"] > checkins.get(n, 1e9) + 5.0:
            left_at[n] = max(left_at.get(n, 0.0), tr["keyframes"][-1]["t"])
    report = []
    for cam in ("cam_2", "cam_1"):
        view = sorted(_views(cam, data[cam]), key=lambda tr: tr["keyframes"][0]["t"])
        for tr in view:
            if tr.get("name"):
                continue
            t0 = tr["keyframes"][0]["t"]
            if cam == "cam_2" and at_door(cam, tr["keyframes"][:3]):
                continue                           # a new arrival: only the door handoff may name it
            first = tr["keyframes"][0]["box"]
            inside = {n for n, t in checkins.items() if t <= t0 and left_at.get(n, 1e9) > t0}
            # who this view sees right now, and where everyone (named or not) was last seen on it
            visible, last = set(), {}
            for o in view:
                if o is tr or o["keyframes"][0]["t"] >= t0:
                    continue
                key = o.get("name") or f"unknown:{o['global_id']}"
                if o["keyframes"][-1]["t"] >= t0:
                    visible.add(key)
                    continue
                if not o.get("name") and o["keyframes"][-1]["t"] - o["keyframes"][0]["t"] < MIN_UNKNOWN_S:
                    continue                       # a short unnamed fragment, not a person of its own
                if t0 - o["keyframes"][-1]["t"] <= MAX_GAP_S and (o.get("name") is None or o["name"] in inside):
                    if key not in last or o["keyframes"][-1]["t"] > last[key]["keyframes"][-1]["t"]:
                        last[key] = o
            lost = {k: o for k, o in last.items() if k not in visible}
            never_seen = sorted(n for n in inside if n not in visible and n not in last
                                and not any(o.get("name") == n for o in view if o["keyframes"][0]["t"] < t0))
            if cam == "cam_1":
                # People in the room who never checked in (e.g. seated before the recording starts) are seen by
                # cam_2 as unnamed tracks; cam_1 cannot tell which glass box is theirs, so each one is a candidate.
                never_seen += sorted(f"unknown on cam_2:{o['global_id']}" for o in data["cam_2"] if not o.get("name")
                                     and o["keyframes"][-1]["t"] - o["keyframes"][0]["t"] >= MIN_UNKNOWN_S
                                     and o["keyframes"][0]["t"] <= t0 and o["keyframes"][-1]["t"] >= t0 - MAX_GAP_S)
            spot = [k for k, o in lost.items() if _near(o["keyframes"][-1]["box"], first)]
            if len(spot) == 1:
                who, why = spot[0], f"same place as its last box on {cam} (ID {lost[spot[0]]['global_id']})"
            elif not spot and len(lost) + len(never_seen) == 1:
                who = next(iter(lost)) if lost else never_seen[0]
                why = "the only person in the room not visible on this view"
            else:
                cands = sorted(lost) + never_seen
                report.append(f"take {take} {cam}: ID {tr['global_id']} at t={t0} s stays Unknown "
                              f"(could be {', '.join(cands) if cands else 'nobody known'})")
                continue
            if who.startswith("unknown"):
                continue                           # it is the unknown person seen there before
            tr["name"], tr["name_from"] = who, t0
            tr["name_source"] = f"room occupancy: {why}"
            report.append(f"take {take} {cam}: ID {tr['global_id']} = {who} from t={t0} s ({why})")
    return report
