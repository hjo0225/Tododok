"""
Discussion 라우터 — 얇은 래퍼.
세션 검증 + context 구성 후 services.discussion.run_discussion에 위임.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.deps import get_current_student
from app.core.supabase import supabase
from app.schemas.llm import PassageGeneration
from app.schemas.session import DiscussionRequest
from app.services.discussion import run_discussion

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/sessions/{session_id}/discussion")
async def discussion(
    session_id: str,
    body: DiscussionRequest,
    request: Request,
    student_id: str = Depends(get_current_student),
):
    # ── 세션 검증 ─────────────────────────────────────────
    session_res = (
        supabase.table("sessions")
        .select("id, student_id, status, passage_id")
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

    # ── context 구성 ──────────────────────────────────────
    context = _build_context(student_id, session_id, session_data["passage_id"])

    # ── SSE 스트리밍 ──────────────────────────────────────
    async def generate():
        try:
            async for event in run_discussion(
                session_id=session_id,
                user_content=body.content,
                context=context,
                demo_mode=body.demo_mode,
            ):
                if await request.is_disconnected():
                    logger.info("클라이언트 연결 끊김: session_id=%s", session_id)
                    return
                yield _sse(event)
        except Exception:
            logger.exception("토의 스트림 실패: session_id=%s", session_id)
            yield _sse({"error": "DISCUSSION_FAILED", "is_final": False})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_context(student_id: str, session_id: str, passage_id: str) -> dict:
    """세션에 필요한 context dict 구성. supabase 동기 호출."""
    student_res = (
        supabase.table("students")
        .select("name, level, weak_areas")
        .eq("id", student_id)
        .single()
        .execute()
    )
    s = student_res.data or {}

    passage_res = (
        supabase.table("passages")
        .select("generated_content")
        .eq("id", passage_id)
        .single()
        .execute()
    )
    passage_content = ""
    if passage_res.data and passage_res.data.get("generated_content"):
        try:
            p = PassageGeneration.model_validate_json(passage_res.data["generated_content"])
            passage_content = p.passage
        except Exception:
            logger.exception("generated_content 파싱 실패: session_id=%s", session_id)

    qr_res = (
        supabase.table("question_results")
        .select("question_type, is_correct")
        .eq("session_id", session_id)
        .execute()
    )
    question_results = qr_res.data or []
    all_correct = all(q.get("is_correct") for q in question_results) if question_results else False

    return {
        "student_name": s.get("name") or "학생",
        "passage_content": passage_content,
        "question_results": question_results,
        "all_correct": all_correct,
        "student_level": s.get("level", 2),
        "weak_areas": s.get("weak_areas") or [],
    }
