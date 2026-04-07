import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.feedback_agent import analyze_discussion
from app.core.constants import (
    LEVEL_DOWN_THRESHOLD,
    LEVEL_UP_THRESHOLD,
    MAX_LEVEL,
    MIN_LEVEL,
    SESSIONS_FOR_LEVEL_ADJUST,
)
from app.core.deps import get_current_student
from app.core.supabase import supabase
from app.schemas.session import QuestionResultOut, SessionEndResponse

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


@router.post("/sessions/{session_id}/end", response_model=SessionEndResponse)
def end_session(
    session_id: str,
    student_id: str = Depends(get_current_student),
):
    # 1. 세션 검증
    session_res = (
        supabase.table("sessions")
        .select("id, student_id, status, session_date")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SESSION_NOT_FOUND")
    session_data = session_res.data
    if session_data["student_id"] != student_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    if session_data["status"] != "in_progress":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="SESSION_NOT_IN_PROGRESS")

    # 2. 토의 발화(user) 추출
    msg_res = (
        supabase.table("messages")
        .select("content")
        .eq("session_id", session_id)
        .eq("speaker", "user")
        .execute()
    )
    user_messages = [m["content"] for m in (msg_res.data or [])]

    # 3. question_results 조회
    qr_res = (
        supabase.table("question_results")
        .select("*")
        .eq("session_id", session_id)
        .execute()
    )
    question_results = qr_res.data or []
    all_correct = all(q.get("is_correct") for q in question_results) if question_results else False

    # 4. 피드백 에이전트 호출
    scores_data = analyze_discussion(
        user_messages=user_messages,
        question_results=[
            {"question_type": q["question_type"], "is_correct": q.get("is_correct")}
            for q in question_results
        ],
    )

    # 5. 세션 completed 처리
    now_iso = datetime.now(timezone.utc).isoformat()
    supabase.table("sessions").update({
        "status": "completed",
        "ended_at": now_iso,
        "all_correct": all_correct,
        "score_reasoning": scores_data["score_reasoning"],
        "score_vocabulary": scores_data["score_vocabulary"],
        "score_context": scores_data["score_context"],
    }).eq("id", session_id).execute()

    # 6. Streak 갱신
    student_res = (
        supabase.table("students")
        .select("streak_count, streak_last_date, teacher_override_level, level")
        .eq("id", student_id)
        .single()
        .execute()
    )
    student = student_res.data or {}

    session_date = date.fromisoformat(session_data["session_date"])
    yesterday = session_date - timedelta(days=1)
    streak_last = student.get("streak_last_date")

    old_streak = student.get("streak_count") or 0
    if streak_last is None:
        new_streak = 1
    elif date.fromisoformat(streak_last) == yesterday:
        new_streak = old_streak + 1
    elif date.fromisoformat(streak_last) == session_date:
        new_streak = old_streak
    else:
        new_streak = 1

    # 7. level 재조정 (teacher_override_level 없을 때만)
    new_level = student.get("level", 2)
    if not student.get("teacher_override_level"):
        recent_res = (
            supabase.table("sessions")
            .select("score_reasoning, score_vocabulary, score_context")
            .eq("student_id", student_id)
            .eq("status", "completed")
            .order("ended_at", desc=True)
            .limit(SESSIONS_FOR_LEVEL_ADJUST)
            .execute()
        )
        recent = recent_res.data or []
        recent_with_current = [
            {
                "score_reasoning": scores_data["score_reasoning"],
                "score_vocabulary": scores_data["score_vocabulary"],
                "score_context": scores_data["score_context"],
            }
        ] + recent
        if len(recent_with_current) >= SESSIONS_FOR_LEVEL_ADJUST:
            avg = sum(
                (r.get("score_reasoning", 0) + r.get("score_vocabulary", 0) + r.get("score_context", 0)) / 3
                for r in recent_with_current[:SESSIONS_FOR_LEVEL_ADJUST]
            ) / SESSIONS_FOR_LEVEL_ADJUST
            if avg >= LEVEL_UP_THRESHOLD and new_level < MAX_LEVEL:
                new_level = new_level + 1
            elif avg <= LEVEL_DOWN_THRESHOLD and new_level > MIN_LEVEL:
                new_level = new_level - 1

    # 8. students UPDATE
    supabase.table("students").update({
        "streak_count": new_streak,
        "streak_last_date": session_date.isoformat(),
        "level": new_level,
    }).eq("id", student_id).execute()

    # 9. 응답 구성
    qr_out = [
        QuestionResultOut(
            question_index=q["question_index"],
            question_type=q["question_type"],
            question_text=q["question_text"],
            choices=q["choices"],
            correct_index=q["correct_index"],
            selected_index=q.get("selected_index"),
            is_correct=q.get("is_correct"),
        )
        for q in sorted(question_results, key=lambda x: x["question_index"])
    ]

    return SessionEndResponse(
        score_reasoning=scores_data["score_reasoning"],
        score_vocabulary=scores_data["score_vocabulary"],
        score_context=scores_data["score_context"],
        feedback=scores_data["feedback"],
        streak_count=new_streak,
        question_results=qr_out,
    )
