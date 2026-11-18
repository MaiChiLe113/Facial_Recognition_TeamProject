"""Student photos: the student card image stored for the student (students.student_card),
read from the shared Drive folder (config.DRIVE_ROOT)."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import DRIVE_ROOT
from ..db.queries import get_student

router = APIRouter(tags=["photos"])


@router.get("/photos/{student_id}")
def photo(student_id: str):
    st = get_student(student_id)
    if not st or not st["student_card"]:
        raise HTTPException(404, f"No photo for {student_id}.")
    path = DRIVE_ROOT / st["student_card"]
    if not path.exists():
        raise HTTPException(404, f"Photo file missing: {st['student_card']}. Check HAWKEYE_DRIVE_ROOT.")
    return FileResponse(path)
