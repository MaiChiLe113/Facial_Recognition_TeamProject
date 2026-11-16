from fastapi import APIRouter

from ..mock_store import build_dashboard

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard")
def dashboard():
    # TODO (Đức Mạnh): read from the database instead of mock files.
    return build_dashboard()
