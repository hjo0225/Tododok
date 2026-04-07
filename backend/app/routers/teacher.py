import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import create_client

from app.core.config import settings
from app.core.deps import get_current_teacher
from app.schemas.classroom import ClassroomCreate, ClassroomCreateResponse, ClassroomItem

router = APIRouter(prefix="/teacher", tags=["teacher"])

MAX_JOIN_CODE_RETRIES = 5


def _service_client():
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _generate_join_code(service) -> str:
    for _ in range(MAX_JOIN_CODE_RETRIES):
        code = secrets.token_urlsafe(4)[:6].upper()
        exists = (
            service.table("classrooms")
            .select("id")
            .eq("join_code", code)
            .maybe_single()
            .execute()
        )
        if exists.data is None:
            return code
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="JOIN_CODE_GENERATION_FAILED",
    )


@router.get("/classrooms", response_model=list[ClassroomItem])
def list_classrooms(teacher_id: str = Depends(get_current_teacher)):
    service = _service_client()

    res = (
        service.table("classrooms")
        .select("id, name, join_code, students(count)")
        .eq("teacher_id", teacher_id)
        .execute()
    )

    result = []
    for row in res.data:
        student_count = row["students"][0]["count"] if row.get("students") else 0
        result.append(
            ClassroomItem(
                id=row["id"],
                name=row["name"],
                join_code=row["join_code"],
                student_count=student_count,
            )
        )
    return result


@router.post("/classrooms", response_model=ClassroomCreateResponse, status_code=status.HTTP_201_CREATED)
def create_classroom(body: ClassroomCreate, teacher_id: str = Depends(get_current_teacher)):
    service = _service_client()

    join_code = _generate_join_code(service)

    res = (
        service.table("classrooms")
        .insert({"name": body.name, "teacher_id": teacher_id, "join_code": join_code})
        .execute()
    )
    row = res.data[0]
    return ClassroomCreateResponse(id=row["id"], join_code=row["join_code"])
