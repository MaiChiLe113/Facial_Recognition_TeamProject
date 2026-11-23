"""The registered faces: one owner for every user of them (Features demo, live cameras, the pipeline's recognize stage).

The same enrolment photos the recorded takes on Home are named from. For every student in the database, the images in
`photo_folder` and the `student_card` image are embedded with ml/face_recognition and kept in memory. They are found
under a folder that contains AppliedML/<name>/ and AppliedML/student_card_image/: the mounted Google Drive or a copy
downloaded into the repo (see _enrolment_root); photos uploaded on the Add person page live in data/photos/.
Embeddings are cached on disk (data/raw/face_embeddings.npz, keyed by file path, size, date and model), so only new
or changed photos cost time after the first load; the backend loads them in the background when it starts.

    load_registered(force=False)   embed the photos (returns at once if a load is already running)
    registered_faces()             ({student_id: [embedding, ...]}, {student_id: name}) for the live cameras
    registered(force=False)        the page view: people, skipped photos, load info, error, loading
    roster_changed()               call after POST /api/students: reloads in the background
    attach(engine)                 keep engine.shared["gallery"] (the recognize stage) equal to the loaded faces

Faces in the photos are found with the pipeline's detector (app/pipeline/detector.detect_faces, YuNet) and cut
with ml_models.crop_face(..., "face_recognition"), exactly as on a live frame.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from ..config import DATA_DIR, DRIVE_ROOT, IMAGE_EXT, REPO_DIR, student_file
from ..core.ml_models import crop_face, load_infer, weights_status
from ..db.queries import list_students

MAX_SIDE = 1600      # phone photos are shrunk before the face search
SEARCH_SIDES = (1600, 960, 640, 480)   # a face that fills a close-up is found at a smaller size
MIN_FACE_PX = 24     # smallest face accepted in an enrolment photo (at the search size)
EMBEDDING_CACHE = DATA_DIR / "raw" / "face_embeddings.npz"

_lock = threading.Lock()
_gallery = {}        # student_id_vn -> [embedding, ...]
_people = {}         # student_id_vn -> {"student_id", "name", "folder_photos" (images in the member's folder),
                     #                   "photos" (embedded and used for recognition), "total" (folder images + card)}
_skipped = []        # [{"student", "file", "reason"}]
_loaded = False
_loading = False
_load_error = None
_load_info = {}      # {"root", "seconds", "cached", "computed"} of the last load
_load_lock = threading.Lock()
_engines = []        # engines whose shared["gallery"] follows the loaded faces (attach)


def is_loading():
    return _loading


def attach(engine):
    """Keep engine.shared["gallery"] equal to the registered faces from now on (and start a load if none ran)."""
    _engines.append(engine)
    engine.shared["gallery"] = registered_faces()[0]
    if not _loaded:
        threading.Thread(target=load_registered, daemon=True, name="gallery-load").start()


def _publish():
    gallery = registered_faces()[0]
    for engine in _engines:
        engine.shared["gallery"] = gallery


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

    if path.suffix.lower() in (".heic", ".heif"):
        from pillow_heif import register_heif_opener   # pip install pillow-heif
        register_heif_opener()
    rgb = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    rgb.thumbnail((MAX_SIDE, MAX_SIDE))
    return np.asarray(rgb)[:, :, ::-1].copy()


def _face_crop(image):
    import cv2
    from ..pipeline.detector import detect_faces

    for side in SEARCH_SIDES:
        scale = min(1.0, side / max(image.shape[:2]))
        small = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image
        boxes = detect_faces(small, min_size=MIN_FACE_PX)
        if boxes:
            return crop_face(small, boxes[0], "face_recognition")
    return None


def _signature():
    """Changes when the model or the face finder changes, which invalidates the cached embeddings."""
    w = weights_status("face_recognition")["weights"]
    try:
        st = os.stat(w)
        model = f"{st.st_size}-{st.st_mtime_ns}"
    except OSError:
        model = "none"
    return f"{model}|yunet"        # the face finder is always the pipeline's YuNet now


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
            folder = student_file(st["photo_folder"], root) if st["photo_folder"] else None
            files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT) if folder and folder.is_dir() else []
            folder_photos = len(files)
            if st["student_card"]:
                files.append(student_file(st["student_card"], root))
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
        _publish()
        _load_info = {"root": str(root), "seconds": round(time.perf_counter() - started, 1),
                      "cached": sum(len(f) for _, _, f in plan) - len(todo), "computed": len(todo)}
    except Exception as e:  # noqa: BLE001 - e.g. the face_recognition weights are missing
        _load_error = f"{type(e).__name__}: {e}"
    finally:
        _loading = False
        _load_lock.release()


def registered_faces():
    """A copy of the loaded registered faces for other users (the live cameras):
    ({student_id: [embedding, ...]}, {student_id: name}). Empty until the first load has finished."""
    with _lock:
        return {sid: list(v) for sid, v in _gallery.items()}, {sid: p["name"] for sid, p in _people.items()}


_reload_wanted = threading.Event()


def roster_changed():
    """Call after the student roster changes (POST /api/students): reloads the registered faces in the background,
    straight away or as soon as a load that is already running ends, so the change is never skipped."""
    _reload_wanted.set()
    threading.Thread(target=_reload_when_free, daemon=True, name="gallery-roster").start()


def _reload_when_free():
    while _reload_wanted.is_set():
        with _load_lock:             # wait for a running load to finish
            pass
        if _reload_wanted.is_set():
            _reload_wanted.clear()
            load_registered(force=True)


def registered(force=False):
    """The registered students for the page: people, photos that were skipped, load info and any error.
    "loading" is true while a load is running (the page polls until it is false)."""
    load_registered(force)
    with _lock:
        return {"people": list(_people.values()), "skipped": list(_skipped), "error": _load_error,
                "loading": _loading, "info": dict(_load_info), "drive_root_exists": _enrolment_root().exists()}
