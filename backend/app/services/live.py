"""Live cameras over Wi-Fi.  Owner: Mai Chi

A phone or laptop opens the Camera page (/camera) and sends JPEG frames over the WebSocket /ws/camera/{cam_id}.
Each frame runs that camera's pipeline from backend/pipeline.json (corridor / classroom: detect people -> track;
doorway: detect faces -> liveness -> recognise -> emotion). The frame is drawn with the results and kept, and the
host's Live page shows every camera as an MJPEG stream (GET /api/live/{cam_id}/stream).

One frame per camera is processed at a time: the sender waits for the answer before sending the next frame, so a
slow host lowers the frame rate instead of building a queue.
"""
import asyncio
import threading
import time
from collections import Counter

BOUNDARY = "frame"
JPEG_QUALITY = 80
STALE_SECONDS = 3.0          # a camera with no frame for this long shows as disconnected
HOLD_SECONDS = 1.5           # a face box is the same face as one seen at most this long ago ...
HOLD_IOU = 0.3               # ... when the two boxes overlap at least this much (name vote, see _vote_names)

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

    def describe(self):
        age = time.time() - self.last_seen if self.last_seen else None
        return {"cam_id": self.cam_id, "connected": age is not None and age < STALE_SECONDS,
                "senders": self.senders, "fps": round(self.fps, 1), "seconds_since_frame": None if age is None else round(age, 1),
                **self.summary}


_cams = {}
_cams_lock = threading.Lock()


def camera(cam_id):
    with _cams_lock:
        return _cams.setdefault(cam_id, LiveCamera(cam_id))


def cameras():
    with _cams_lock:
        return list(_cams.values())


def _faces_for(engine, role):
    """Point the doorway pipeline at the registered faces (the same gallery the Features demo uses)."""
    if role != "attendance":
        return {}
    from . import features_demo
    gallery, names = features_demo.registered_faces()
    if not gallery:
        threading.Thread(target=features_demo.load_registered, daemon=True).start()   # returns at once if loading
    engine.shared["gallery"] = gallery
    return names


def _label(img, x, y, text, color):
    import cv2
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    y0 = max(0, y - th - 8)
    cv2.rectangle(img, (x, y0), (x + tw + 8, y0 + th + 8), color, -1)
    cv2.putText(img, text, (x + 4, y0 + th + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)


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
        best["box"], best["t"] = f["box"], now
        if f.get("student_id"):
            best["votes"][f["student_id"]] += 1
        if f.get("live") is False or not best["votes"]:
            continue
        top = best["votes"].most_common(1)[0][0]
        f["held"] = top != f.get("student_id")
        f["student_id"] = top


def _draw(img, ctx, names):
    """Boxes and labels on the frame. Returns the JSON summary of what was found."""
    import cv2
    people, faces = [], []
    for tr in ctx.tracks:
        x, y, w, h = (int(v) for v in tr["box"])
        tid = tr.get("global_id", tr.get("local_id"))
        color = _COLORS[tid % len(_COLORS)] if tid is not None else _UNKNOWN
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        _label(img, x, y, f"ID {tid}", color)
        people.append({"id": tid, "box": [x, y, w, h]})
    for f in ctx.faces:
        x, y, w, h = (int(v) for v in f["box"])
        name = names.get(f.get("student_id")) if f.get("student_id") else None
        live = f.get("live")
        color = _BAD if live is False else (_OK if name else _UNKNOWN)
        parts = ["Spoof" if live is False else (name or "Unknown")]
        if f.get("emotion"):
            parts.append(f["emotion"])
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        _label(img, x, y, " | ".join(parts), color)
        faces.append({"box": [x, y, w, h], "name": name, "student_id": f.get("student_id"), "live": live,
                      "liveness_score": f.get("liveness_score"), "similarity": f.get("similarity"),
                      "emotion": f.get("emotion"), "held": bool(f.get("held"))})
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
        names = _faces_for(engine, pipeline.role)
        now = time.time()
        started = time.perf_counter()
        ctx = engine.process_frame(cam_id, img, now)
        _vote_names(cam, ctx.faces, now)
        summary = _draw(img, ctx, names)
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
