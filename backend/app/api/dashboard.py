from fastapi import APIRouter

from ..db.queries import build_dashboard

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard")
def dashboard():
    # Records come from SQLite; attendance-cam status and map positions are still mock (live pipeline state).
    return build_dashboard()
