"""Student photos: the student card (students.student_card) from the shared Drive folder, or for a student
registered on the Add person page the first uploaded photo (data/photos/<student_id_vn>/)."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import BROWSER_IMAGE_EXT, student_file
from ..db.queries import get_student

router = APIRouter(tags=["photos"])


@router.get("/photos/{student_id}")
def photo(student_id: str):
    st = get_student(student_id)
    if not st or not st["photo"]:
        raise HTTPException(404, f"No photo for {student_id}.")
    if st["student_card"]:
        path = student_file(st["student_card"])
    else:
        folder = student_file(st["photo_folder"])
        path = next((p for p in sorted(folder.glob("*")) if p.suffix.lower() in BROWSER_IMAGE_EXT), None)
    if path is None or not path.is_file():
        raise HTTPException(404, f"Photo file missing for {student_id}. Check HAWKEYE_DRIVE_ROOT.")
    return FileResponse(path)
