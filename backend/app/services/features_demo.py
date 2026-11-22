"""Backs the Features demo page: run the three basic models on one webcam frame.

    face_recognition  who is it (against the registered students, see below)
    anti_spoofing     live or spoof (printed photo / phone screen)
    emotion           the facial expression

The models come from ml/<feature>/infer.py + <feature>.pt (see app/core/ml_models.py). A feature
whose weights or libraries are missing is reported in "errors" and the others still run.
Faces are found with OpenCV's YuNet (ml/face_recognition/models/face_detection_yunet_2023mar.onnx, the same
detector MultiCam uses; see ml/face_recognition/README.md) or, if that file is missing, the weaker Haar cascade.
This is only for the demo (the pipeline's detector is Mai Chi's).

Registered faces: the same enrolment photos MultiCam names people from. For every student in the
database, the images in `photo_folder` and the `student_card` image are embedded and kept in memory.
They are found under a folder that contains AppliedML/<name>/ and AppliedML/student_card_image/: the
mounted Google Drive or a copy downloaded into the repo (see _enrolment_root). Embeddings are cached on
disk (data/raw/face_embeddings.npz, keyed by file path, size, date and model), so only new or changed
photos cost time after the first load, and the backend loads them in the background when it starts.
"""
import csv
import json
import os
import threading
import time
from datetime import datetime
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from ..config import DATA_DIR, DRIVE_ROOT, REPO_DIR
from ..core.ml_models import FEATURES, ML_DIR, load_infer, weights_status
from ..db.queries import list_students

# Crop margin around the detected face box, per feature (anti_spoofing is trained with 25 %, see ml/anti_spoofing/try_liveness.py).
MARGIN = {"face_recognition": 0.1, "anti_spoofing": 0.25, "emotion": 0.0}
LIVENESS_FRAMES = 10

_lock = threading.Lock()
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
MAX_SIDE = 1600      # phone photos are shrunk before the face search
SEARCH_SIDES = (1600, 960, 640, 480)   # a face that fills a close-up is found at a smaller size

_gallery = {}        # student_id_vn -> [embedding, ...]
_people = {}         # student_id_vn -> {"student_id", "name", "folder_photos" (images in the member's folder),
                     #                   "photos" (embedded and used for recognition), "total" (folder images + card)}
_skipped = []        # [{"student", "file", "reason"}]
_loaded = False
_loading = False
_load_error = None
_load_info = {}      # {"root", "seconds", "cached", "computed"} of the last load
_load_lock = threading.Lock()
EMBEDDING_CACHE = DATA_DIR / "raw" / "face_embeddings.npz"
LOG_DIR = REPO_DIR / "logs"          # root/logs/, git-ignored
LOG_COLUMNS = ["time", "client", "features", "face", "name", "student_id", "similarity", "live", "liveness_score",
               "emotion", "emotion_score", "box_x", "box_y", "box_w", "box_h", "frame_ms", "errors"]
_log_lock = threading.Lock()
_live_buffers = {}   # client id -> deque of recent crops of the main face
_cascade = None
_yunet = None
_yunet_lock = threading.Lock()
YUNET_FILE = ML_DIR / "face_recognition" / "models" / "face_detection_yunet_2023mar.onnx"


def _find_faces(image, min_size=60):
    """[(x, y, w, h), ...] in pixels, largest first."""
    global _cascade, _yunet
    import cv2

    if YUNET_FILE.is_file() and hasattr(cv2, "FaceDetectorYN"):
        with _yunet_lock:
            if _yunet is None:
                _yunet = cv2.FaceDetectorYN.create(str(YUNET_FILE), "", (320, 320), 0.8)
            h, w = image.shape[:2]
            _yunet.setInputSize((w, h))
            _, rows = _yunet.detect(image)
        boxes = [] if rows is None else [(max(0, int(r[0])), max(0, int(r[1])), int(r[2]), int(r[3])) for r in rows]
        return sorted((b for b in boxes if min(b[2], b[3]) >= min_size * 0.6), key=lambda b: -b[2] * b[3])
    if _cascade is None:
        local = ML_DIR / "anti_spoofing" / "haarcascade_frontalface_default.xml"
        path = str(local) if local.is_file() else cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _cascade = cv2.CascadeClassifier(path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    found = _cascade.detectMultiScale(gray, 1.1, 5, minSize=(min_size, min_size))
    return sorted(((int(x), int(y), int(w), int(h)) for x, y, w, h in found), key=lambda b: -b[2] * b[3])


def _crop(image, box, margin):
    h, w = image.shape[:2]
    x, y, bw, bh = box
    return image[int(max(0, y - bh * margin)):int(min(h, y + bh * (1 + margin))),
                 int(max(0, x - bw * margin)):int(min(w, x + bw * (1 + margin)))]


def decode(jpeg_bytes):
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The body is not a decodable image (send a JPEG or PNG).")
    return image


def status():
    """Per feature: are the weights where the app looks for them, and is the code importable."""
    out = []
    for feature in FEATURES:
        info = weights_status(feature)
        try:
            load_infer(feature)
            info["code"] = True
        except Exception as e:  # noqa: BLE001
            info["code"] = False
            info["error"] = f"{type(e).__name__}: {e}"
        info["registered_faces"] = len(_gallery) if feature == "face_recognition" else None
        out.append(info)
    return out


def analyze(image, features, client="default"):
    """Run the selected features on one BGR frame. Returns {"faces": [...], "errors": {...}, "ms": ...}."""
    start = time.perf_counter()
    height, width = image.shape[:2]
    boxes = _find_faces(image)
    faces = [{"box": [x / width, y / height, w / width, h / height]} for x, y, w, h in boxes]
    errors = {}

    def run(feature, fn):
        try:
            fn(load_infer(feature))
        except Exception as e:  # noqa: BLE001 - a missing model must not stop the others
            errors[feature] = f"{type(e).__name__}: {e}"

    if "anti_spoofing" in features:
        def live(infer):
            with _lock:
                buffer = _live_buffers.setdefault(client, deque(maxlen=LIVENESS_FRAMES))
                if not boxes:
                    buffer.clear()
                    return
                buffer.append(_crop(image, boxes[0], MARGIN["anti_spoofing"]))
                crops = list(buffer)
            result = infer.check(crops)           # the largest face; smoothed over the last frames
            faces[0].update(live=bool(result["live"]), liveness_score=result.get("score"))
        run("anti_spoofing", live)

    if "face_recognition" in features and boxes:
        def recognise(infer):
            load_registered()
            if _loading:                     # first load still running: do not block the frame
                for face in faces:
                    face.update(student_id=None, name=None, similarity=0.0, registered=False, loading=True)
                return
            with _lock:
                gallery = {sid: list(vectors) for sid, vectors in _gallery.items()}
            for face, box in zip(faces, boxes):
                student_id, similarity = infer.identify(_crop(image, box, MARGIN["face_recognition"]), gallery, None)
                face.update(student_id=student_id, name=_people[student_id]["name"] if student_id else None,
                            similarity=similarity, registered=bool(gallery))
        run("face_recognition", recognise)

    if "emotion" in features:
        def feel(infer):
            if not boxes:
                infer.reset()
                return
            for face, box in zip(faces, boxes):
                result = infer.predict(_crop(image, box, MARGIN["emotion"]))
                face.update(emotion=result["label"], emotion_score=result.get("score"))
        run("emotion", feel)

    return {"faces": faces, "errors": errors, "ms": round((time.perf_counter() - start) * 1000, 1)}


def _enrolment_root():
    """The folder that holds AppliedML/: the configured Drive root (HAWKEYE_DRIVE_ROOT, or two levels above
    HAWKEYE_VIDEO_ROOT), else the repo folder when AppliedML/ was downloaded into it."""
    for root in (DRIVE_ROOT, REPO_DIR):
        if (root / "AppliedML").is_dir():
            return root
    return DRIVE_ROOT


def _read_photo(path):
    """Any enrolment photo (JPEG, PNG, HEIC from a phone) as a BGR array, upright, at most MAX_SIDE px."""
    import numpy as np
    from PIL import Image, ImageOps

    if path.suffix.lower() == ".heic":
        from pillow_heif import register_heif_opener   # pip install pillow-heif
        register_heif_opener()
    rgb = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    rgb.thumbnail((MAX_SIDE, MAX_SIDE))
    return np.asarray(rgb)[:, :, ::-1].copy()


def _face_crop(image):
    import cv2

    for side in SEARCH_SIDES:
        scale = min(1.0, side / max(image.shape[:2]))
        small = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image
        boxes = _find_faces(small, min_size=40)
        if boxes:
            return _crop(small, boxes[0], MARGIN["face_recognition"])
    return None


def _signature():
    """Changes when the model or the face finder changes, which invalidates the cached embeddings."""
    w = weights_status("face_recognition")["weights"]
    try:
        st = os.stat(w)
        model = f"{st.st_size}-{st.st_mtime_ns}"
    except OSError:
        model = "none"
    return f"{model}|{'yunet' if YUNET_FILE.is_file() else 'haar'}"


def _read_cache():
    import numpy as np

    try:
        with np.load(EMBEDDING_CACHE, allow_pickle=False) as z:
            keys, vecs, ok = json.loads(str(z["keys"])), z["vectors"], z["found"]
        return {k: (vecs[i] if ok[i] else None) for i, k in enumerate(keys)}
    except Exception:  # noqa: BLE001 - no cache yet, or a damaged one: start again
        return {}


def _write_cache(cache):
    import numpy as np

    try:
        EMBEDDING_CACHE.parent.mkdir(parents=True, exist_ok=True)
        keys = list(cache)
        vecs = np.stack([cache[k] if cache[k] is not None else np.zeros(512, np.float32) for k in keys]) if keys \
            else np.zeros((0, 512), np.float32)
        tmp = EMBEDDING_CACHE.with_name(EMBEDDING_CACHE.stem + ".tmp.npz")
        np.savez(tmp, keys=json.dumps(keys), vectors=vecs, found=np.array([cache[k] is not None for k in keys]))
        tmp.replace(EMBEDDING_CACHE)
    except Exception:  # noqa: BLE001 - a read-only disk only costs speed
        pass


def load_registered(force=False):
    """Embed every student's enrolment photos into the registered faces (cached on disk, see the module doc)."""
    global _loaded, _loading, _load_error, _load_info
    if not _load_lock.acquire(blocking=False):
        return                       # another thread is loading; callers see _loading
    try:
        if _loaded and not force:
            return
        _loading, _loaded, _load_error = True, True, None
        started = time.perf_counter()
        root = _enrolment_root()
        sig = _signature()
        infer = load_infer("face_recognition")
        students = list_students()

        plan = []                    # (student, folder_photos, [files])
        for st in students:
            folder = root / st["photo_folder"] if st["photo_folder"] else None
            files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT) if folder and folder.is_dir() else []
            folder_photos = len(files)
            if st["student_card"]:
                files.append(root / st["student_card"])
            plan.append((st, folder_photos, [f for f in files if f.name.lower() != "desktop.ini"]))

        cache = _read_cache()
        keys = {}                    # file -> cache key (None: unreadable)
        todo = []
        for _, _, files in plan:
            for f in files:
                try:
                    stat = f.stat()
                    keys[f] = f"{f.relative_to(root) if f.is_relative_to(root) else f}|{stat.st_size}|{stat.st_mtime_ns}|{sig}"
                except OSError:
                    keys[f] = None
                if keys[f] is not None and keys[f] not in cache:
                    todo.append(f)

        errors = {}

        def work(f):
            try:
                crop = _face_crop(_read_photo(f))
                cache[keys[f]] = infer.embed(crop) if crop is not None else None
            except Exception as e:  # noqa: BLE001 - one bad photo (e.g. HEIC without pillow-heif) must not stop the rest
                errors[f] = f"{type(e).__name__}: {e}"[:120]

        if todo:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(work, todo))
            live_keys = {k for k in keys.values() if k}
            _write_cache({k: v for k, v in cache.items() if k in live_keys})

        gallery, people, skipped = {}, {}, []
        for st, folder_photos, files in plan:
            vectors = []
            for f in files:
                k = keys.get(f)
                if k is None or not f.is_file():
                    skipped.append({"student": st["name"], "file": f.name, "reason": "file not found"})
                elif f in errors:
                    skipped.append({"student": st["name"], "file": f.name, "reason": errors[f]})
                elif cache.get(k) is None:
                    skipped.append({"student": st["name"], "file": f.name, "reason": "no face found"})
                else:
                    vectors.append(cache[k])
            if vectors:
                gallery[st["student_id_vn"]] = vectors
            people[st["student_id_vn"]] = {"student_id": st["student_id_vn"], "name": st["name"],
                                           "folder_photos": folder_photos, "photos": len(vectors), "total": len(files)}
        with _lock:
            _gallery.clear(); _gallery.update(gallery)
            _people.clear(); _people.update(people)
            _skipped[:] = skipped
        _load_info = {"root": str(root), "seconds": round(time.perf_counter() - started, 1),
                      "cached": sum(len(f) for _, _, f in plan) - len(todo), "computed": len(todo)}
    except Exception as e:  # noqa: BLE001 - e.g. the face_recognition weights are missing
        _load_error = f"{type(e).__name__}: {e}"
    finally:
        _loading = False
        _load_lock.release()


def _warm_up():
    """Load every model whose weights file exists (so the first webcam frame is not slow), then the registered faces."""
    for feature in FEATURES:
        try:
            if weights_status(feature)["found"]:
                load_infer(feature)._load()
        except Exception:  # noqa: BLE001 - reported later by /api/features-demo/status or in the frame result
            pass
    registered()


def start_preload():
    """Warm up the models and load the registered faces in a background thread (called when the backend starts)."""
    threading.Thread(target=_warm_up, daemon=True, name="features-demo-warmup").start()


def registered(force=False):
    """The registered students for the page: people, photos that were skipped, load info and any error.
    "loading" is true while a load is running (the page polls until it is false)."""
    load_registered(force)
    with _lock:
        return {"people": list(_people.values()), "skipped": list(_skipped), "error": _load_error,
                "loading": _loading, "info": dict(_load_info), "drive_root_exists": _enrolment_root().exists()}


def frame_log_rows(result, features, client):
    """The log rows of one analysed frame: one per face, or one blank row (face = 0) when there is none.
    The page keeps these for the whole camera session and shows them; see save_session_log()."""
    def cell(v, digits=None):
        return "" if v is None else (round(v, digits) if digits is not None and isinstance(v, float) else v)

    base = {"time": datetime.now().isoformat(timespec="milliseconds"), "client": client, "features": "+".join(features),
            "frame_ms": result.get("ms"), "errors": "; ".join(f"{k}: {v}" for k, v in result.get("errors", {}).items())}
    rows = []
    for i, f in enumerate(result.get("faces", []), 1):
        x, y, w, h = f["box"]
        rows.append({**base, "face": i, "name": cell(f.get("name")), "student_id": cell(f.get("student_id")),
                     "similarity": cell(f.get("similarity"), 4), "live": cell(f.get("live")),
                     "liveness_score": cell(f.get("liveness_score"), 4), "emotion": cell(f.get("emotion")),
                     "emotion_score": cell(f.get("emotion_score"), 4),
                     "box_x": round(x, 4), "box_y": round(y, 4), "box_w": round(w, 4), "box_h": round(h, 4)})
    return rows or [{**base, "face": 0}]


def save_session_log(rows, started=None):
    """Write one camera session (camera on -> off) to logs/features_demo_<start>.csv. Returns the path
    relative to the repo ("logs/features_demo_2026-11-23_004512.csv"), or None when there is nothing to save."""
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return None
    try:
        start = datetime.fromisoformat(str(started).replace("Z", "+00:00")).astimezone() if started else datetime.now()
    except ValueError:
        start = datetime.now()
    with _log_lock:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"features_demo_{start:%Y-%m-%d_%H%M%S}.csv"
        n = 2
        while path.exists():                       # two sessions that started in the same second
            path = LOG_DIR / f"features_demo_{start:%Y-%m-%d_%H%M%S}_{n}.csv"
            n += 1
        with path.open("w", newline="", encoding="utf-8-sig") as fh:   # BOM: Excel reads Vietnamese names
            writer = csv.DictWriter(fh, fieldnames=LOG_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    return f"logs/{path.name}"
