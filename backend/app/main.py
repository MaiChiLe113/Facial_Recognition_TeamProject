"""Hawkeye API.

Run: uvicorn app.main:app --reload --port 8000   (from the backend/ folder)

This file only builds the app. Routes live in app/api/ (one file per area).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import ROUTERS

app = FastAPI(title="Hawkeye")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for router in ROUTERS:
    app.include_router(router)


# TODO (Đức Mạnh): live mode
# - WebSocket /ws/camera/{cam_id}: receive frames from the browser camera pages
# - WebSocket /ws/dashboard: push boxes, events and map positions to the UI
# - POST /api/students: registration from the "+ Add person" page
