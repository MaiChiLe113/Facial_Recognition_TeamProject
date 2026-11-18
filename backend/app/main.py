"""Hawkeye API.

Run: uvicorn app.main:app --reload --port 8000   (from the backend/ folder)

This file only builds the app. Routes live in app/api/ (one file per area), the per-frame
pipeline in app/core/ (configured by backend/pipeline.json), add-ons in app/features/.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import ROUTERS
from .core.engine import Engine
from .db import init_db

log = logging.getLogger("hawkeye")


@asynccontextmanager
async def lifespan(app):
    # If the pipeline cannot start, keep serving the dashboard and demo; /api/pipeline/status says why.
    # SQLite: create the tables; a new database is seeded from data/mock/.
    if init_db():
        log.info("Seeded the database from data/mock/")
    app.state.engine, app.state.engine_error = None, None
    try:
        engine = Engine.load().start()
        app.state.engine = engine
        for name, feature in engine.features.items():
            if getattr(feature, "router", None) is not None and feature.status == "ready":
                app.include_router(feature.router, prefix=f"/api/features/{name}", tags=[f"feature: {name}"])
    except Exception as e:  # noqa: BLE001
        app.state.engine_error = f"{type(e).__name__}: {e}"
        log.exception("Pipeline engine did not start")
    yield


app = FastAPI(title="Hawkeye", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for router in ROUTERS:
    app.include_router(router)


# TODO (Đức Mạnh): live mode
# - WebSocket /ws/camera/{cam_id}: receive frames, call app.state.engine.process_frame(cam_id, image, t)
# - WebSocket /ws/dashboard: push boxes, events and map positions to the UI (subscribe to the event bus)
# - POST /api/students: registration from the "+ Add person" page
