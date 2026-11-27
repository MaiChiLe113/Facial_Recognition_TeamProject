"""System log of the model files the app infers with (System log page, GET /api/system/models).

For every model: the file the app loads (the same path and HAWKEYE_*_WEIGHTS override the loaders use), its last
modified time, size, a SHA-256 fingerprint, and the version label from ml/model_versions.json (edited by hand).

Change history: logs/model_changes.jsonl (git-ignored, per machine). One line is appended whenever a model's
fingerprint or version label differs from the last line for that model, checked at startup and on every request.
The first line per model is "first seen" (the date this machine started tracking it), not when it was trained.
"""
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..config import REPO_DIR
from ..core.ml_models import weights_file

VERSIONS_FILE = REPO_DIR / "ml" / "model_versions.json"
LOG_FILE = REPO_DIR / "logs" / "model_changes.jsonl"

_lock = threading.Lock()
_hash_cache = {}            # path -> (size, mtime_ns, sha256): a 45 MB file is only hashed again after it changes


def _env_path(env, default):
    value = os.getenv(env)
    return Path(value).expanduser() if value else default


def models():
    """(key, label, path) of every model file the app infers with."""
    return [
        ("face_recognition", "Face recognition", weights_file("face_recognition")),
        ("anti_spoofing", "Anti-spoofing (liveness)", weights_file("anti_spoofing")),
        ("emotion", "Emotion", weights_file("emotion")),
        ("face_quality", "Face quality (AI enrolment scan)", weights_file("face_quality")),
        ("glasses_detection", "Glasses detection", weights_file("glasses_detection")),
        ("presence_verification", "Presence verification + door audit",
         _env_path("HAWKEYE_PRESENCE_VERIFICATION_WEIGHTS", REPO_DIR / "ml" / "presence_verification" / "presence_verification.joblib")),
        ("face_detector", "Face detector (YuNet)",
         _env_path("HAWKEYE_FACE_DETECTOR", REPO_DIR / "ml" / "face_recognition" / "models" / "face_detection_yunet_2023mar.onnx")),
        ("person_detector", "Person detector (YOLO11n)", _env_path("HAWKEYE_PERSON_DETECTOR", REPO_DIR / "ml" / "tracking" / "yolo11n.pt")),
    ]


def _versions():
    try:
        return json.loads(VERSIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _sha256(path, size, mtime_ns):
    key = str(path)
    hit = _hash_cache.get(key)
    if hit and hit[:2] == (size, mtime_ns):
        return hit[2]
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    _hash_cache[key] = (size, mtime_ns, h.hexdigest())
    return h.hexdigest()


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat(timespec="seconds")


def _rel(path):
    try:
        return path.resolve().relative_to(REPO_DIR.resolve()).as_posix()
    except ValueError:
        return str(path)          # an override outside the repo


def current():
    """The models as they are on disk now."""
    versions = _versions()
    out = []
    for key, label, path in models():
        v = versions.get(key, {})
        row = {"key": key, "label": label, "file": _rel(path), "found": path.is_file(),
               "version": v.get("version"), "note": v.get("note"), "modified": None, "size": None, "sha256": None}
        if row["found"]:
            st = path.stat()
            row.update(modified=_iso(st.st_mtime), size=st.st_size, sha256=_sha256(path, st.st_size, st.st_mtime_ns))
        out.append(row)
    return out


def history():
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def check():
    """Compare the models on disk with the last logged state; append a line for each change. Returns current()."""
    with _lock:
        now = current()
        last = {}
        for entry in history():
            last[entry["key"]] = entry
        new = []
        for m in now:
            prev = last.get(m["key"])
            state = (m["sha256"], m["version"])
            if prev and (prev.get("sha256"), prev.get("version")) == state:
                continue
            if prev is None and not m["found"]:
                continue                       # never seen and still missing: nothing to log
            if prev is None:
                change = "first seen"
            elif not m["found"]:
                change = "file missing"
            elif prev.get("sha256") != m["sha256"]:
                change = "file replaced"
            else:
                change = "version label changed"
            new.append({"detected": datetime.now().astimezone().isoformat(timespec="seconds"), "key": m["key"],
                        "label": m["label"], "change": change, "version": m["version"], "previous_version": prev and prev.get("version"),
                        "file": m["file"], "modified": m["modified"], "size": m["size"], "sha256": m["sha256"]})
        if new:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                for entry in new:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return now
