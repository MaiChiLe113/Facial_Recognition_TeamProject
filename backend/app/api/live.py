"""Live cameras over Wi-Fi (see app/services/live.py and docs/LAN_DEMO.md).

    WS   /ws/camera/{cam_id}        a phone / laptop sends JPEG frames (binary); each answer is the frame's summary
    GET  /api/live                  every camera from backend/pipeline.json: connected, fps, people, faces, host_urls
    GET  /api/live/{cam_id}/stream  MJPEG of the camera's annotated frames (for an <img>)
    POST /api/live/{cam_id}/remove  host removes the camera: its senders are closed (code 4001) and it shows idle
"""
import socket

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from ..services import live
from ..services.videos import video_config

router = APIRouter(tags=["live"])
FRONTEND_PORT = 5173


def _engine(app):
    engine = getattr(app.state, "engine", None)
    if engine is None:
        raise HTTPException(503, getattr(app.state, "engine_error", None) or "Pipeline engine not started")
    return engine


def _lan_ip():
    """This machine's address on the local network (no packet is sent: a UDP connect only picks the route)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 9))        # TEST-NET-1, never routed
            return s.getsockname()[0]
        except OSError:
            return None


@router.get("/api/live")
def live_status(request: Request):
    engine = _engine(request.app)
    labels = {c["cam_id"]: c for c in video_config()["cameras"]}
    out = []
    for cam_id, pipeline in engine.pipelines.items():
        meta = labels.get(cam_id, {})
        out.append({"label": meta.get("label", cam_id), "place": meta.get("place"), "role": pipeline.role,
                    **live.camera(cam_id).describe()})
    ip = _lan_ip()
    return {"cameras": out, "host_urls": [f"https://{ip}:{FRONTEND_PORT}/camera"] if ip else []}


@router.get("/api/live/{cam_id}/stream")
def live_stream(cam_id: str, request: Request):
    if cam_id not in _engine(request.app).pipelines:
        raise HTTPException(404, f"Unknown camera '{cam_id}'")
    return StreamingResponse(live.mjpeg(cam_id), media_type=f"multipart/x-mixed-replace; boundary={live.BOUNDARY}",
                             headers={"Cache-Control": "no-store"})


@router.post("/api/live/{cam_id}/remove")
def live_remove(cam_id: str, request: Request):
    if cam_id not in _engine(request.app).pipelines:
        raise HTTPException(404, f"Unknown camera '{cam_id}'")
    live.camera(cam_id).remove()
    return {"cam_id": cam_id, "removed": True}


REMOVED = 4001      # close code: the host removed this camera (the Camera page stops instead of reconnecting)


@router.websocket("/ws/camera/{cam_id}")
async def camera_socket(ws: WebSocket, cam_id: str):
    engine = getattr(ws.app.state, "engine", None)
    if engine is None or cam_id not in engine.pipelines:
        await ws.close(code=4404, reason=f"Unknown camera '{cam_id}'")
        return
    await ws.accept()
    cam = live.camera(cam_id)
    cam.senders += 1
    joined = cam.removed
    try:
        while cam.removed == joined:
            frame = await ws.receive_bytes()
            summary = await run_in_threadpool(live.process, engine, cam_id, frame)
            if cam.removed != joined:
                break
            await ws.send_json(summary)
        cam.clear()                         # a frame in flight when Remove was pressed must not light it up again
        await ws.close(code=REMOVED, reason="Removed by the host")
    except WebSocketDisconnect:
        pass
    finally:
        cam.senders -= 1
