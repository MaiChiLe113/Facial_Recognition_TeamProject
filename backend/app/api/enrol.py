"""AI face scan for the Add person page (app/services/enrol.py). New routes only; nothing existing changes.

    POST /api/enrol/session                      start a scan -> summary (session_id, slots, threshold, model)
    POST /api/enrol/frame   (multipart)          session_id, image, final=false|true -> analysis + hint
    POST /api/enrol/video   (multipart)          session_id, video -> summary + counts of why frames were refused
    GET  /api/enrol/session/{id}                 summary (kept stills per slot, missing slots, liveness, duplicate)
    GET  /api/enrol/session/{id}/still/{slot}/{i}  a kept still (JPEG) for the review screen
    DELETE /api/enrol/session/{id}               discard a scan

Finish with POST /api/students and enrol_session=<id> instead of photos.
"""
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from ..services import enrol

router = APIRouter(prefix="/api/enrol", tags=["enrol"])

MAX_FRAME_BYTES = 15 * 2**20
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v"}


def _session(sid):
    try:
        return enrol.get(sid)
    except KeyError:
        raise HTTPException(404, "scan session not found or expired; start a new scan") from None


@router.post("/session", status_code=201)
def start(source: str = Form("live")):
    if source not in ("live", "video"):
        raise HTTPException(422, "source must be live or video")
    return enrol.summary(enrol.get(enrol.new_session(source)))


@router.get("/session/{sid}")
def status(sid: str):
    return enrol.summary(_session(sid))


@router.delete("/session/{sid}", status_code=204)
def discard(sid: str):
    enrol.drop(sid)


@router.post("/session/{sid}/fail")
def fail(sid: str, reason: str = Form(...), attempts: int = Form(3), reasons: str = Form("{}")):
    import json
    try:
        counts = json.loads(reasons)
    except ValueError:
        counts = {}
    enrol.fail(_session(sid), reason, attempts, counts if isinstance(counts, dict) else {})
    return enrol.summary(_session(sid))


@router.get("/session/{sid}/still/{slot}/{index}")
def still(sid: str, slot: str, index: int):
    s = _session(sid)
    if slot not in enrol.SLOTS or not 0 <= index < len(s["slots"][slot]):
        raise HTTPException(404, "no such still")
    return Response(enrol.still_jpeg(s, slot, index), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/frame")
async def frame(session_id: str = Form(...), image: UploadFile = File(...), final: bool = Form(False)):
    s = _session(session_id)
    data = await image.read(MAX_FRAME_BYTES + 1)
    if len(data) > MAX_FRAME_BYTES:
        raise HTTPException(413, "frame is too large")
    try:
        img = enrol.decode_image(data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return await run_in_threadpool(enrol.analyse, s, img, final)


@router.post("/video")
async def video(session_id: str = Form(...), video: UploadFile = File(...)):
    s = _session(session_id)
    ext = Path(video.filename or "").suffix.lower()
    if ext not in VIDEO_EXT:
        raise HTTPException(422, f"{video.filename}: not a video ({', '.join(sorted(VIDEO_EXT))})")
    with tempfile.TemporaryDirectory(prefix="hawkeye_enrol_") as tmp:
        path = Path(tmp) / f"upload{ext}"
        size = 0
        with path.open("wb") as f:
            while chunk := await video.read(1 << 20):
                size += len(chunk)
                if size > enrol.VIDEO_MAX_BYTES:
                    raise HTTPException(413, f"video is larger than {enrol.VIDEO_MAX_BYTES // 2**20} MB")
                f.write(chunk)
        try:
            counts = await run_in_threadpool(enrol.scan_video, s, path)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    return {**enrol.summary(s), "frame_reasons": counts}
