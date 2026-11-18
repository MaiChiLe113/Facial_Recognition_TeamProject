"""HTTP routes, one router per area. main.py includes every router listed in ROUTERS.

To add an area: create app/api/<area>.py with `router = APIRouter()`, then add it below.
Existing response shapes are a contract with the frontend (README, "Data contract"): add fields, never rename or remove.
"""
from . import dashboard, demo, photos, pipeline, records, system

ROUTERS = [system.router, dashboard.router, demo.router, pipeline.router, photos.router, records.router]
