"""Students, courses and sessions from the SQLite database (app/db)."""
import json
import re
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..config import IMAGE_EXT, PHOTOS_DIR, PHOTOS_REL
from ..db import queries

router = APIRouter(tags=["records"])

MAX_PHOTOS = 20                     # the Add person page asks for 10-20
MAX_PHOTO_BYTES = 15 * 1024 * 1024


@router.get("/api/students")
def students():
    return queries.list_students()


@router.post("/api/students", status_code=201)
def create_student(name: str = Form(...), student_id_vn: str = Form(...), student_id_au: str = Form(""),
                   year: str = Form(""), courses: str = Form("[]"), photos: list[UploadFile] = File(...)):
    """Register a student from the Add person page: details + face photos (multipart form).
    Photos go to data/photos/<student_id_vn>/; the face gallery reloads so the student is recognised right away."""
    sid, name, au = student_id_vn.strip().upper(), name.strip(), student_id_au.strip()
    if not name:
        raise HTTPException(422, "name is empty")
    if not re.fullmatch(r"SWH\d{5}", sid):          # same rules as frontend/src/pages/AddPerson.vue
        raise HTTPException(422, "student_id_vn must be SWH followed by 5 digits, e.g. SWH02701")
    if au and not re.fullmatch(r"\d{9}", au):
        raise HTTPException(422, "student_id_au must be 9 digits")
    try:
        keys = json.loads(courses or "[]")
        if not isinstance(keys, list) or not all(isinstance(k, int) for k in keys):
            raise ValueError
    except ValueError:
        raise HTTPException(422, "courses must be a JSON list of course keys, e.g. [1, 2]")
    if not 1 <= len(photos) <= MAX_PHOTOS:
        raise HTTPException(422, f"send 1 to {MAX_PHOTOS} photos")
    for p in photos:
        if Path(p.filename or "").suffix.lower() not in IMAGE_EXT:
            raise HTTPException(422, f"{p.filename}: not a photo ({', '.join(sorted(IMAGE_EXT))})")
    if queries.get_student(sid):                    # checked before touching data/photos/<sid>/
        raise HTTPException(409, f"{sid} is already registered")

    folder = PHOTOS_DIR / sid
    if folder.exists():
        shutil.rmtree(folder)       # left over from an earlier failed registration
    folder.mkdir(parents=True)
    try:
        for i, p in enumerate(photos, 1):
            data = p.file.read(MAX_PHOTO_BYTES + 1)
            if len(data) > MAX_PHOTO_BYTES:
                raise HTTPException(413, f"{p.filename} is larger than {MAX_PHOTO_BYTES // 2**20} MB")
            (folder / f"photo_{i:02d}{Path(p.filename).suffix.lower()}").write_bytes(data)
        saved = queries.create_student({"student_id_vn": sid, "name": name, "student_id_au": au, "year": year.strip(),
                                        "courses": keys, "photo_folder": f"{PHOTOS_REL}/{sid}"})
    except BaseException as e:
        shutil.rmtree(folder, ignore_errors=True)  # nothing half-registered is left behind
        if isinstance(e, queries.AlreadyExists):
            raise HTTPException(409, str(e)) from e
        if isinstance(e, ValueError):
            raise HTTPException(422, str(e)) from e
        raise

    from ..services import gallery
    gallery.roster_changed()                       # the new student is recognised once the photos are embedded
    return saved


@router.get("/api/courses")
def courses():
    return queries.list_courses()


@router.get("/api/sessions")
def sessions():
    """Newest first, each with its attendance rows and events."""
    return queries.list_sessions()


class AttendanceChange(BaseModel):
    status: Optional[str] = None
    attended: Optional[bool] = None


@router.patch("/api/sessions/{session_id}/attendance/{student_id}")
def change_attendance(session_id: int, student_id: str, body: AttendanceChange):
    """Manual change from the History page. Send only the fields to change; attended: null = back to the rule."""
    try:
        return queries.update_attendance(session_id, student_id, body.model_dump(exclude_unset=True))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
