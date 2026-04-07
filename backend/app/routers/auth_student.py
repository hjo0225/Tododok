from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from pydantic import BaseModel
from supabase import create_client

from app.core.config import settings

router = APIRouter(prefix="/auth/student", tags=["auth-student"])

STUDENT_TOKEN_EXPIRE_DAYS = 30


class StudentJoinRequest(BaseModel):
    name: str
    join_code: str


class StudentJoinResponse(BaseModel):
    student_id: str
    access_token: str


def _service_client():
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _issue_student_token(student_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=STUDENT_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": student_id, "type": "student", "exp": exp},
        settings.JWT_SECRET,
        algorithm="HS256",
    )


@router.post("/join", response_model=StudentJoinResponse, status_code=status.HTTP_201_CREATED)
def student_join(body: StudentJoinRequest):
    service = _service_client()

    # join_code로 classroom 조회
    classroom = (
        service.table("classrooms")
        .select("id")
        .eq("join_code", body.join_code.upper())
        .maybe_single()
        .execute()
    )
    if classroom.data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CLASSROOM_NOT_FOUND")

    classroom_id = classroom.data["id"]

    # students 테이블에 INSERT
    res = (
        service.table("students")
        .insert({"classroom_id": classroom_id, "name": body.name, "level": 2})
        .execute()
    )
    student_id = res.data[0]["id"]

    return StudentJoinResponse(
        student_id=student_id,
        access_token=_issue_student_token(student_id),
    )
