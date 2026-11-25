"""Live cameras over Wi-Fi.  Owner: Mai Chi

A phone or laptop opens the Camera page (/camera) and sends JPEG frames over the WebSocket /ws/camera/{cam_id}.
Each frame runs that camera's pipeline from backend/pipeline.json: every camera detects faces -> liveness ->
recognise -> emotion (always on); corridor / classroom also detect and track people. Only the doorway checks in. The frame is drawn with the results and kept, and the
host's Home page (Live source) shows every camera as an MJPEG stream (GET /api/live/{cam_id}/stream).

One frame per camera is processed at a time: the sender waits for the answer before sending the next frame, so a
slow host lowers the frame rate instead of building a queue.
"""
import asyncio
import threading
import time
from collections import Counter, deque

BOUNDARY = "frame"
JPEG_QUALITY = 80
STALE_SECONDS = 3.0          # a camera with no frame for this long shows as disconnected
HOLD_SECONDS = 1.5           # a face box is the same face as one seen at most this long ago ...
HOLD_IOU = 0.3               # ... when the two boxes overlap at least this much (name vote, see _vote_names)
FORGET_PERSON_S = 10.0       # a person track not seen for this long is forgotten (door crossings)
SMOOTH_ALPHA = 0.6           # live box smoothing: weight of the newest box (only past frames exist live, so it
                             # trails by under 0.1 s at ~10 fps); boxes older than HOLD_SECONDS are not mixed in
HANDOFF_S = 3.0              # door handoff: a check-in names the one track at the door within this many seconds of it

_COLORS = [(66, 135, 245), (52, 199, 89), (255, 149, 0), (175, 82, 222), (255, 59, 48), (90, 200, 250)]   # BGR
_OK, _BAD, _UNKNOWN = (80, 190, 80), (60, 60, 230), (0, 170, 255)


class LiveCamera:
    def __init__(self, cam_id):
        self.cam_id = cam_id
        self.lock = threading.Lock()        # one frame at a time: the tracker and liveness buffer keep state
        self.jpeg = None                    # newest annotated frame
        self.seq = 0                        # bumps with every new frame (the MJPEG stream waits on it)
        self.summary = {}
        self.last_seen = 0.0
        self.fps = 0.0
        self.senders = 0
        self.face_tracks = []               # [{box, t, votes}] faces linked across frames (name vote)
        self.removed = 0                    # bumps when the host removes the camera; open senders are closed
        self.people = {}                    # track id -> {"zone", "t"} (door crossings)
        self.door_events = deque(maxlen=30)  # [{seq, t, id, event}] door crossings, newest last
        self.door_seq = 0
        self.door_seen = deque(maxlen=400)  # [(t, track id)] while a person stands in the door zone (door handoff)

    def remove(self):
        """Host pressed "Remove": drop the picture and status; camera_socket closes every sender (code 4001)."""
        with self.lock:
            self.removed += 1
            self.clear()

    def clear(self):
        self.jpeg, self.summary, self.last_seen, self.fps, self.face_tracks = None, {}, 0.0, 0.0, []
        self.people = {}
        self.door_events.clear()
        self.door_seen.clear()

    def describe(self):
        age = time.time() - self.last_seen if self.last_seen else None
        return {"cam_id": self.cam_id, "connected": age is not None and age < STALE_SECONDS,
                "senders": self.senders, "fps": round(self.fps, 1), "seconds_since_frame": None if age is None else round(age, 1),
                **self.summary, "door_events": [_door_text(ev) for ev in self.door_events]}


_cams = {}
_cams_lock = threading.Lock()


def camera(cam_id):
    with _cams_lock:
        return _cams.setdefault(cam_id, LiveCamera(cam_id))


def cameras():
    with _cams_lock:
        return list(_cams.values())


def _names_for(role):
    """Names of the registered students (every camera recognises faces). The recognize stage reads the faces themselves from
    engine.shared["gallery"], which app/services/gallery.py keeps current (gallery.attach in main.py)."""
    from . import gallery
    faces, names = gallery.registered_faces()
    if not faces:
        threading.Thread(target=gallery.load_registered, daemon=True).start()   # returns at once if loading
    return names


def _smooth(state, box, now):
    """Running average of one person's / face's box across frames (kept in `state`), so boxes stop jittering."""
    prev = state.get("sbox")
    if prev is not None and now - state.get("st", now) <= HOLD_SECONDS:
        box = tuple(SMOOTH_ALPHA * b + (1 - SMOOTH_ALPHA) * p for b, p in zip(box, prev))
    state["sbox"], state["st"] = tuple(box), now
    return box


def _draw_labels(img, labels):
    """labels: [(x, y, w, h, text, color, priority)] of drawn boxes. Each label takes the first free spot of: above its
    box, just inside its top, under it, then further down, so no two labels overlap (higher priority chooses first)."""
    import cv2
    height, width = img.shape[:2]
    placed = []
    hits = lambda r: any(r[0] < q[0] + q[2] and q[0] < r[0] + r[2] and r[1] < q[1] + q[3] and q[1] < r[1] + r[3] for q in placed)
    for x, y, w, h, text, color, _ in sorted(labels, key=lambda lab: -lab[6]):
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        lw, lh = tw + 8, th + 8
        lx = max(0, min(x, width - lw))
        spots = [y - lh - 2, y + 2, y + h + 2] + [y + 2 + (i + 1) * (lh + 2) for i in range(8)]
        ly = next((sy for sy in (max(0, min(v, height - lh)) for v in spots) if not hits((lx, sy, lw, lh))),
                  max(0, y - lh - 2))
        placed.append((lx, ly, lw, lh))
        cv2.rectangle(img, (lx, ly), (lx + lw, ly + lh), color, -1)
        cv2.putText(img, text, (lx + 4, ly + th + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw, ih = max(0, min(ax + aw, bx + bw) - max(ax, bx)), max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    return inter / (aw * ah + bw * bh - inter) if inter else 0.0


def _vote_names(cam, faces, now):
    """Recognition runs on single frames, so its answer flickers (Unknown, or a look-alike, on some frames). Faces are
    linked across frames by box overlap (a gap of at most HOLD_SECONDS); each link keeps a count of the names recognised
    on it, and the face shows the most frequent one ("held" when this frame's own answer differs). Spoofs show no name."""
    cam.face_tracks = [tr for tr in cam.face_tracks if now - tr["t"] <= HOLD_SECONDS]
    free = list(cam.face_tracks)
    for f in faces:
        best = max(free, key=lambda tr: _iou(tr["box"], f["box"]), default=None)
        if best is None or _iou(best["box"], f["box"]) < HOLD_IOU:
            best = {"votes": Counter()}
            cam.face_tracks.append(best)
        else:
            free.remove(best)
        smoothed = _smooth(best, f["box"], now)   # link on the raw box, show the smoothed one
        best["box"], best["t"] = f["box"], now
        f["box"] = smoothed
        if f.get("student_id"):
            best["votes"][f["student_id"]] += 1
        if f.get("live") is False or not best["votes"]:
            continue
        top = best["votes"].most_common(1)[0][0]
        f["held"] = top != f.get("student_id")
        f["student_id"] = top


_projection = {}


def _to_map(cam_id, box, width, height):
    """Map position (fractions of the Room 204 map) of a person box in pixels, from the calibrated floor homographies
    (ml/presence_verification/trajectories.to_map, the same projection as the recorded trails), or None when the
    camera has no homography, the feet are not visible, or the module cannot load."""
    if "to_map" not in _projection:
        try:
            import sys
            from ..config import REPO_DIR
            folder = str(REPO_DIR / "ml" / "presence_verification")
            if folder not in sys.path:
                sys.path.insert(0, folder)
            from trajectories import to_map            # noqa: E402 (ml/ module, imported by path)
            _projection["to_map"] = to_map
        except Exception:  # noqa: BLE001 - no map positions, the rest of live mode still works
            _projection["to_map"] = None
    to_map = _projection["to_map"]
    if to_map is None:
        return None
    x, y, w, h = box
    xy = to_map(cam_id, [x / width, y / height, w / width, h / height])
    return [round(xy[0], 4), round(xy[1], 4)] if xy else None


_ZONE_OF = {}


def _zone(xy):
    """corridor / door / room for a map position (presence verification's zone_of), or None."""
    if xy is None:
        return None
    if "zone_of" not in _ZONE_OF:
        try:
            from trajectories import zone_of          # on sys.path once _to_map has loaded the module
            _ZONE_OF["zone_of"] = zone_of
        except Exception:  # noqa: BLE001
            _ZONE_OF["zone_of"] = None
    return _ZONE_OF["zone_of"](*xy) if _ZONE_OF["zone_of"] else None


# ---- door handoff: the doorway's check-in names the corridor / classroom track at the door (live link_names.py) ----
_checkins = deque(maxlen=50)      # [(t, student_id, name)] named, live faces on the doorway camera
_checkins_lock = threading.Lock()


def _record_checkins(faces, names, now):
    """Remember who the doorway camera recognises (after the name vote), for the door handoff."""
    with _checkins_lock:
        for f in faces:
            sid = f.get("student_id")
            if not sid or f.get("live") is False:
                continue
            if _checkins and _checkins[-1][1] == sid and now - _checkins[-1][0] < 1.0:
                _checkins[-1] = (now, sid, names.get(sid, sid))
            else:
                _checkins.append((now, sid, names.get(sid, sid)))


def _handoff(cam, now):
    """Name this camera's track that stood in the door zone when someone checked in: only when exactly one track was
    there within HANDOFF_S of the check-in (several people at the door: no name rather than a wrong one). A name
    sticks to its track and is not given to a second live track on the same camera."""
    with _checkins_lock:
        recent = [c for c in _checkins if now - c[0] <= 2 * HANDOFF_S]
    for t_c, sid, name in recent:
        near = {tid for t, tid in cam.door_seen if abs(t - t_c) <= HANDOFF_S}
        if len(near) != 1:
            continue
        st = cam.people.get(next(iter(near)))
        if st is None or st.get("sid"):
            continue
        if any(o.get("sid") == sid and now - o["t"] <= STALE_SECONDS for o in cam.people.values()):
            continue
        st["sid"], st["name"] = sid, name
        for ev in cam.door_events:                      # crossings logged before the name was known
            if ev["id"] == next(iter(near)):
                ev["name"] = name


def _door_text(ev):
    who = f"{ev['name']} (ID {ev['id']})" if ev.get("name") else f"ID {ev['id']}"
    return {**ev, "event": f"{who} {ev['action']}"}


def _door_crossing(cam, role, tid, zone, now):
    """Update a person's zone. Returns "entered the classroom" / "left the classroom" when the track
    moves between this camera's side of the door (corridor for the corridor camera, room for the classroom camera)
    and the door zone, else None."""
    st = cam.people.setdefault(tid, {"zone": None, "t": now})
    st["t"] = now
    if zone is None:
        return None
    prev, st["zone"] = st["zone"], zone
    if zone == "door":
        cam.door_seen.append((now, tid))
    if prev is None or prev == zone:
        return None
    own = "corridor" if role == "outside" else "room"
    if {prev, zone} == {"corridor", "room"}:
        return "entered the classroom" if zone == "room" else "left the classroom"
    if (prev, zone) == (own, "door"):
        return "entered the classroom" if own == "corridor" else "left the classroom"
    if (prev, zone) == ("door", own):
        return "left the classroom" if own == "corridor" else "entered the classroom"
    return None


def _draw(img, ctx, names, role=None, cam=None, now=None):
    """Boxes and labels on the frame. Returns the JSON summary of what was found."""
    import cv2
    height, width = img.shape[:2]
    people, faces, labels = [], [], []
    for tr in ctx.tracks:
        tid = tr.get("global_id", tr.get("local_id"))
        state = cam.people.setdefault(tid, {"zone": None, "t": now}) if cam is not None else {}
        x, y, w, h = (int(v) for v in _smooth(state, tr["box"], now))
        xy = _to_map(ctx.cam_id, (x, y, w, h), width, height)
        if cam is not None:
            crossing = _door_crossing(cam, role, tid, _zone(xy), now)
            if crossing:
                cam.door_seq += 1
                cam.door_events.append({"seq": cam.door_seq, "t": now, "id": tid, "action": crossing,
                                        "name": cam.people[tid].get("name")})
        color = _COLORS[tid % len(_COLORS)] if tid is not None else _UNKNOWN
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        person = cam.people.get(tid, {}) if cam is not None else {}
        labels.append((x, y, w, h, f"ID {tid} | {person['name']}" if person.get("name") else f"ID {tid}", color,
                       1 if person.get("name") else 0))
        people.append({"id": tid, "box": [x, y, w, h], "map": xy, "name": person.get("name"),
                       "student_id": person.get("sid")})
    for f in ctx.faces:
        x, y, w, h = (int(v) for v in f["box"])
        name = names.get(f.get("student_id")) if f.get("student_id") else None
        live = f.get("live")
        color = _BAD if live is False else (_OK if name else _UNKNOWN)
        parts = ["Spoof" if live is False else (name or "Unknown")]
        if f.get("emotion"):
            parts.append(f["emotion"])
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        labels.append((x, y, w, h, " | ".join(parts), color, 2))
        faces.append({"box": [x, y, w, h], "name": name, "student_id": f.get("student_id"), "live": live,
                      "liveness_score": f.get("liveness_score"), "similarity": f.get("similarity"),
                      "emotion": f.get("emotion"), "held": bool(f.get("held"))})
        if "glasses" in f:
            faces[-1].update(glasses=f["glasses"], glasses_score=f["glasses_score"])
    _draw_labels(img, labels)
    return {"people": people, "faces": faces}


def process(engine, cam_id, data):
    """Run one JPEG frame from a sender through the camera's pipeline. Returns the summary sent back to it."""
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return {"error": "not a JPEG frame"}
    cam = camera(cam_id)
    pipeline = engine.pipelines[cam_id]
    with cam.lock:
        names = _names_for(pipeline.role)
        now = time.time()
        started = time.perf_counter()
        ctx = engine.process_frame(cam_id, img, now)
        _vote_names(cam, ctx.faces, now)
        cam.people = {k: v for k, v in cam.people.items() if now - v["t"] <= FORGET_PERSON_S}
        if pipeline.role == "attendance":
            _record_checkins(ctx.faces, names, now)
        summary = _draw(img, ctx, names, pipeline.role, cam, now)
        if pipeline.role in ("outside", "inside"):
            _handoff(cam, now)
        ok, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if cam.last_seen:
            cam.fps = 0.8 * cam.fps + 0.2 / max(now - cam.last_seen, 1e-3)
        cam.last_seen = now
        cam.summary = {**summary, "role": pipeline.role, "frame_ms": round((time.perf_counter() - started) * 1000)}
        if ok:
            cam.jpeg, cam.seq = jpeg.tobytes(), cam.seq + 1
        return cam.summary


async def mjpeg(cam_id):
    """multipart/x-mixed-replace stream of the camera's annotated frames (an <img> shows it as video)."""
    cam, last = camera(cam_id), -1
    while True:
        if cam.seq != last and cam.jpeg is not None:
            last, jpeg = cam.seq, cam.jpeg
            yield (f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n").encode() + jpeg + b"\r\n"
        await asyncio.sleep(0.03)
