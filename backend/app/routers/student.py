import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import create_client

from app.agents.diagnosis_agent import diagnose_student
from app.agents.passage_agent import generate_passage_and_questions
from app.core.config import settings
from app.core.deps import get_current_student
from app.schemas.session import (
    AnswerSubmitRequest,
    AnswerSubmitResponse,
    PassageOut,
    QuestionOut,
    SessionStartResponse,
)

router = APIRouter(prefix="/student", tags=["student"])


def _service_client():
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


# ──────────────────────────────────────────────
# GET /student/sessions/today-count
# ──────────────────────────────────────────────
@router.get("/sessions/today-count")
def today_session_count(student_id: str = Depends(get_current_student)):
    service = _service_client()
    today = date.today().isoformat()
    res = (
        service.table("sessions")
        .select("id", count="exact")
        .eq("student_id", student_id)
        .eq("session_date", today)
        .neq("status", "abandoned")
        .execute()
    )
    return {"count": res.count or 0}


# ──────────────────────────────────────────────
# POST /student/sessions
# ──────────────────────────────────────────────
@router.post("/sessions", response_model=SessionStartResponse, status_code=status.HTTP_201_CREATED)
def start_session(student_id: str = Depends(get_current_student)):
    service = _service_client()
    today = date.today().isoformat()

    # 1. 오늘 세션 수 확인
    count_res = (
        service.table("sessions")
        .select("id", count="exact")
        .eq("student_id", student_id)
        .eq("session_date", today)
        .neq("status", "abandoned")
        .execute()
    )
    today_count = count_res.count or 0
    if today_count >= 3:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="DAILY_LIMIT_REACHED")

    daily_index = today_count + 1

    # 2. 학생 정보 조회
    student_res = (
        service.table("students")
        .select("level, teacher_override_level")
        .eq("id", student_id)
        .single()
        .execute()
    )
    if not student_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="STUDENT_NOT_FOUND")

    student = student_res.data
    difficulty = student["teacher_override_level"] if student["teacher_override_level"] else student["level"]

    # 3. 직전 세션의 passage_id 조회 (제외용)
    last_session_res = (
        service.table("sessions")
        .select("passage_id")
        .eq("student_id", student_id)
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    last_passage_id = (
        last_session_res.data[0]["passage_id"] if last_session_res.data else None
    )

    # 4. passage 선택 (difficulty 매칭 + 직전 제외)
    passage_query = (
        service.table("passages")
        .select("*")
        .eq("difficulty", difficulty)
    )
    if last_passage_id:
        passage_query = passage_query.neq("id", last_passage_id)

    passage_res = passage_query.execute()

    if not passage_res.data:
        # 제외 없이 재시도
        passage_res = (
            service.table("passages")
            .select("*")
            .eq("difficulty", difficulty)
            .execute()
        )
    if not passage_res.data:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="NO_PASSAGE_AVAILABLE")

    # 랜덤 선택
    import random
    passage = random.choice(passage_res.data)

    # 5. generated_content 없으면 생성
    if not passage.get("generated_content"):
        try:
            generated = generate_passage_and_questions(
                difficulty=passage["difficulty"],
                genre=passage["genre"],
                topic=passage["topic"],
                structure_prompt=passage["structure_prompt"],
            )
        except RuntimeError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GENERATION_FAILED")

        content_json = json.dumps(generated, ensure_ascii=False)
        service.table("passages").update({"generated_content": content_json}).eq("id", passage["id"]).execute()
        passage["generated_content"] = content_json

    content_data = json.loads(passage["generated_content"])

    # 6. session INSERT
    now_iso = datetime.now(timezone.utc).isoformat()
    session_res = (
        service.table("sessions")
        .insert({
            "student_id": student_id,
            "passage_id": passage["id"],
            "status": "in_progress",
            "session_date": today,
            "daily_index": daily_index,
            "started_at": now_iso,
        })
        .execute()
    )
    session_id = session_res.data[0]["id"]

    # 7. question_results 3개 INSERT
    for i, q in enumerate(content_data["questions"]):
        service.table("question_results").insert({
            "session_id": session_id,
            "question_index": i + 1,
            "question_type": q["type"],
            "question_text": q["question"],
            "choices": q["choices"],
            "correct_index": q["correct_index"],
            "selected_index": None,
            "is_correct": None,
        }).execute()

    # 8. 응답 구성
    questions_out = [
        QuestionOut(
            index=i + 1,
            type=q["type"],
            text=q["question"],
            choices=q["choices"],
        )
        for i, q in enumerate(content_data["questions"])
    ]
    passage_out = PassageOut(
        title=passage["title"],
        genre=passage["genre"],
        difficulty=passage["difficulty"],
        content=content_data["passage"],
    )

    return SessionStartResponse(
        session_id=session_id,
        passage=passage_out,
        questions=questions_out,
    )


# ──────────────────────────────────────────────
# POST /student/sessions/{session_id}/answer
# ──────────────────────────────────────────────
@router.post("/sessions/{session_id}/answer", response_model=AnswerSubmitResponse)
def submit_answer(
    session_id: str,
    body: AnswerSubmitRequest,
    student_id: str = Depends(get_current_student),
):
    service = _service_client()

    # 1. 세션 검증
    session_res = (
        service.table("sessions")
        .select("id, student_id, status")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SESSION_NOT_FOUND")
    session = session_res.data
    if session["student_id"] != student_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    if session["status"] != "in_progress":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="SESSION_NOT_IN_PROGRESS")

    # 2. 입력 검증
    if body.question_index not in (1, 2, 3):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="INVALID_QUESTION_INDEX")
    if body.selected_index not in (0, 1, 2):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="INVALID_SELECTED_INDEX")

    # 3. question_results 조회
    qr_res = (
        service.table("question_results")
        .select("id, correct_index")
        .eq("session_id", session_id)
        .eq("question_index", body.question_index)
        .maybe_single()
        .execute()
    )
    if not qr_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QUESTION_NOT_FOUND")

    correct_index = qr_res.data["correct_index"]
    is_correct = body.selected_index == correct_index

    # 4. question_results UPDATE
    service.table("question_results").update({
        "selected_index": body.selected_index,
        "is_correct": is_correct,
    }).eq("id", qr_res.data["id"]).execute()

    # 5. 3문제 모두 답했는지 확인
    answered_res = (
        service.table("question_results")
        .select("is_correct, question_type")
        .eq("session_id", session_id)
        .not_.is_("is_correct", "null")
        .execute()
    )
    if len(answered_res.data) == 3:
        _maybe_diagnose(student_id, session_id, answered_res.data, service)

    return AnswerSubmitResponse(ok=True)


def _maybe_diagnose(student_id: str, session_id: str, answered: list[dict], service) -> None:
    """첫 세션이면 진단 에이전트를 실행하고 세션을 completed로 마킹한다."""
    completed_res = (
        service.table("sessions")
        .select("id", count="exact")
        .eq("student_id", student_id)
        .eq("status", "completed")
        .execute()
    )
    if (completed_res.count or 0) > 0:
        return  # 이미 완료된 세션이 있으면 진단 불필요

    # 첫 세션 진단 실행
    try:
        result = diagnose_student([
            {"question_type": r["question_type"], "is_correct": r["is_correct"]}
            for r in answered
        ])
        service.table("students").update({
            "level": result["level"],
            "weak_areas": result["weak_areas"],
        }).eq("id", student_id).execute()
    except RuntimeError:
        pass  # 진단 실패해도 세션은 계속 진행

    # 첫 세션 completed 마킹 (이후 진단 재실행 방지)
    service.table("sessions").update({"status": "completed"}).eq("id", session_id).execute()
