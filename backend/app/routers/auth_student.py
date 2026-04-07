from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from pydantic import BaseModel

from app.core.config import settings
from app.core.constants import STUDENT_TOKEN_EXPIRE_DAYS
from app.core.supabase import supabase

router = APIRouter(prefix="/auth/student", tags=["auth-student"])


class StudentJoinRequest(BaseModel):
    name: str
    join_code: str


class StudentJoinResponse(BaseModel):
    student_id: str
    access_token: str


def _issue_student_token(student_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=STUDENT_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": student_id, "type": "student", "exp": exp},
        settings.JWT_SECRET,
        algorithm="HS256",
    )


@router.post("/join", response_model=StudentJoinResponse, status_code=status.HTTP_201_CREATED)
def student_join(body: StudentJoinRequest):
    classroom = (
        supabase.table("classrooms")
        .select("id")
        .eq("join_code", body.join_code.upper())
        .maybe_single()
        .execute()
    )
    if classroom.data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CLASSROOM_NOT_FOUND")

    classroom_id = classroom.data["id"]

    res = (
        supabase.table("students")
        .insert({"classroom_id": classroom_id, "name": body.name, "level": 2})
        .execute()
    )
    student_id = res.data[0]["id"]

    return StudentJoinResponse(
        student_id=student_id,
        access_token=_issue_student_token(student_id),
    )
