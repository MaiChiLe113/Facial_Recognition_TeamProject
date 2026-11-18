"""Students, courses and sessions from the SQLite database (app/db)."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import queries

router = APIRouter(tags=["records"])


@router.get("/api/students")
def students():
    return queries.list_students()


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
