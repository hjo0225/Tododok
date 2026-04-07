import secrets
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import create_client

from app.core.config import settings
from app.core.dependencies import get_current_teacher
from app.schemas.auth import TeacherProfile
from app.schemas.classroom import (
    ClassroomCreate,
    ClassroomCreateResponse,
    ClassroomItem,
    DashboardResponse,
    LevelOverrideRequest,
    ScoreHistoryItem,
    StudentDashboardItem,
)

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
def list_classrooms(current: TeacherProfile = Depends(get_current_teacher)):
    service = _service_client()

    res = (
        service.table("classrooms")
        .select("id, name, join_code, students(count)")
        .eq("teacher_id", current.user_id)
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
def create_classroom(body: ClassroomCreate, current: TeacherProfile = Depends(get_current_teacher)):
    service = _service_client()

    join_code = _generate_join_code(service)

    res = (
        service.table("classrooms")
        .insert({"name": body.name, "teacher_id": current.user_id, "join_code": join_code})
        .execute()
    )
    row = res.data[0]
    return ClassroomCreateResponse(id=row["id"], join_code=row["join_code"])


@router.get("/classrooms/{classroom_id}/dashboard", response_model=DashboardResponse)
def get_dashboard(classroom_id: str, current: TeacherProfile = Depends(get_current_teacher)):
    service = _service_client()

    # 소유권 확인
    classroom_res = (
        service.table("classrooms")
        .select("id, name")
        .eq("id", classroom_id)
        .eq("teacher_id", current.user_id)
        .maybe_single()
        .execute()
    )
    if classroom_res.data is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

    classroom_name = classroom_res.data["name"]

    # 학생 목록 조회
    students_res = (
        service.table("students")
        .select("id, name, level, teacher_override_level, weak_areas, streak_count")
        .eq("classroom_id", classroom_id)
        .execute()
    )

    four_weeks_ago = (datetime.now() - timedelta(weeks=4)).date().isoformat()

    student_items: list[StudentDashboardItem] = []
    for s in students_res.data:
        # 세션 이력 조회 (최근 4주, completed)
        sessions_res = (
            service.table("sessions")
            .select("session_date, score_reasoning, score_vocabulary, score_context")
            .eq("student_id", s["id"])
            .eq("status", "completed")
            .gte("session_date", four_weeks_ago)
            .not_.is_("score_reasoning", "null")
            .order("session_date", desc=True)
            .execute()
        )
        sessions = sessions_res.data or []

        # 최근 3세션 평균
        recent_sessions = sessions[:3]
        if recent_sessions:
            recent_avg = round(
                sum(
                    (
                        (sess["score_reasoning"] or 0)
                        + (sess["score_vocabulary"] or 0)
                        + (sess["score_context"] or 0)
                    )
                    / 3
                    for sess in recent_sessions
                )
                / len(recent_sessions),
                1,
            )
        else:
            recent_avg = None

        # 날짜별 평균 집계 (4주 이력)
        date_scores: dict[str, list[float]] = defaultdict(list)
        for sess in sessions:
            if (
                sess["score_reasoning"] is not None
                and sess["score_vocabulary"] is not None
                and sess["score_context"] is not None
            ):
                avg = (sess["score_reasoning"] + sess["score_vocabulary"] + sess["score_context"]) / 3
                date_scores[sess["session_date"]].append(avg)

        score_history = [
            ScoreHistoryItem(date=d, avg_score=round(sum(v) / len(v), 1))
            for d, v in sorted(date_scores.items())
        ]

        student_items.append(
            StudentDashboardItem(
                id=s["id"],
                name=s["name"],
                level=s["level"],
                teacher_override_level=s.get("teacher_override_level"),
                weak_areas=s.get("weak_areas") or [],
                streak_count=s.get("streak_count") or 0,
                recent_avg=recent_avg,
                needs_attention=recent_avg is not None and recent_avg <= 5,
                score_history=score_history,
            )
        )

    return DashboardResponse(classroom_name=classroom_name, students=student_items)


@router.patch("/students/{student_id}/level")
def override_student_level(
    student_id: str,
    body: LevelOverrideRequest,
    current: TeacherProfile = Depends(get_current_teacher),
):
    service = _service_client()

    # 해당 teacher 학급 소속 확인
    student_res = (
        service.table("students")
        .select("id, classroom_id")
        .eq("id", student_id)
        .maybe_single()
        .execute()
    )
    if student_res.data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="STUDENT_NOT_FOUND")

    classroom_res = (
        service.table("classrooms")
        .select("id")
        .eq("id", student_res.data["classroom_id"])
        .eq("teacher_id", current.user_id)
        .maybe_single()
        .execute()
    )
    if classroom_res.data is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

    service.table("students").update({"teacher_override_level": body.level}).eq("id", student_id).execute()
    return {"ok": True}
