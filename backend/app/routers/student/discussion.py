"""
Discussion 라우터 — P5 SSE 프로토콜 확장.

POST /sessions/{id}/discussion  : 기존 호환 유지 (fetch 기반 SSE)
GET  /sessions/{id}/discussion  : EventSource 호환 SSE
  - 30초 heartbeat
  - 클라이언트 disconnect 감지 → 백그라운드 task 취소
  - token을 query param으로 수락 (EventSource는 헤더 설정 불가)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt

from app.core.config import settings
from app.core.deps import get_current_student
from app.core.state import create_channel, remove_channel
from app.core.supabase import supabase
from app.schemas.llm import PassageGeneration
from app.schemas.session import DiscussionRequest
from app.services.discussion import run_discussion

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}
_HEARTBEAT_INTERVAL = 30  # seconds


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SSE 포맷 헬퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _heartbeat() -> str:
    return _sse({"type": "heartbeat", "ts": datetime.now(timezone.utc).isoformat()})


def _error(code: str, message: str = "") -> str:
    return _sse({"type": "error", "code": code, "message": message})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  인증 — query param 토큰 (GET SSE 전용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _decode_student_token(token: str) -> str:
    """JWT 검증 → student_id 반환. 실패 시 HTTPException."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        if payload.get("type") != "student":
            raise ValueError("not a student token")
        student_id: str | None = payload.get("sub")
        if not student_id:
            raise ValueError("missing sub")
        return student_id
    except (JWTError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_TOKEN") from e


def get_student_from_query(token: str = Query(..., description="학생 JWT")) -> str:
    return _decode_student_token(token)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  공통: 세션 검증 + context 구성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _validate_session(session_id: str, student_id: str) -> dict:
    """세션 조회·소유권·상태 검증. 실패 시 HTTPException."""
    res = (
        supabase.table("sessions")
        .select("id, student_id, status, passage_id")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SESSION_NOT_FOUND")
    data = res.data
    if data["student_id"] != student_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    if data["status"] != "in_progress":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="SESSION_NOT_IN_PROGRESS")
    return data


def _build_context(student_id: str, session_id: str, passage_id: str) -> dict:
    """세션 context dict 구성. supabase 동기 호출 3회."""
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GET — EventSource 호환 SSE (heartbeat + disconnect cancel)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/sessions/{session_id}/discussion")
async def discussion_sse_get(
    session_id: str,
    request: Request,
    demo_mode: bool = Query(default=False, description="데모 모드"),
    student_id: str = Depends(get_student_from_query),
):
    """
    EventSource 호환 SSE 엔드포인트 (P6 지속 연결).

    - 세션 전체를 하나의 SSE 연결로 유지한다.
    - 학생 입력은 POST /discussion/turns 로 별도 수신 후 큐로 전달.
    - 30초마다 heartbeat 전송.
    - 클라이언트 disconnect 시 채널 정리.
    """
    session_data = _validate_session(session_id, student_id)
    context = _build_context(student_id, session_id, session_data["passage_id"])

    # 세션 채널 생성 (turns 엔드포인트와 공유)
    ch = create_channel(session_id)

    async def generate():
        hb_task: asyncio.Task | None = None

        async def _heartbeat() -> None:
            while True:
                await asyncio.sleep(_HEARTBEAT_INTERVAL)
                # heartbeat는 직접 yield 할 수 없으므로 채널 큐를 거치지 않고
                # 별도 큐에 쓴다 — 아래 inner_queue 참고
                await inner_queue.put({"type": "heartbeat", "ts": datetime.now(timezone.utc).isoformat()})

        inner_queue: asyncio.Queue = asyncio.Queue()

        try:
            hb_task = asyncio.create_task(_heartbeat())

            # ── 토의 라운드 루프 ───────────────────────────
            # run_discussion 은 wait_for_user / is_final / close 중 하나를 내보내고 종료.
            # 각 라운드마다 새로 호출하며, DB 이력에서 상태를 재구성한다.
            user_content = ""  # 첫 라운드: 학생 발화 없음

            while True:
                if await request.is_disconnected():
                    logger.info("GET SSE disconnect: session_id=%s", session_id)
                    return

                # ── 라운드 실행 ────────────────────────────
                got_waiting = False
                got_final = False

                async def _run_round() -> None:
                    nonlocal got_waiting, got_final
                    try:
                        async for event in run_discussion(
                            session_id=session_id,
                            user_content=user_content,
                            context=context,
                            demo_mode=demo_mode,
                        ):
                            await inner_queue.put(event)
                            if event.get("type") == "waiting_for_user":
                                got_waiting = True
                            elif event.get("type") == "is_final":
                                got_final = True
                    except Exception:
                        logger.exception("run_discussion 실패: session_id=%s", session_id)
                        await inner_queue.put({"type": "error", "code": "llm_failure", "message": "토의 생성 실패"})
                    finally:
                        await inner_queue.put(None)  # 라운드 종료 신호

                prod_task = asyncio.create_task(_run_round())

                # ── 이벤트 drain ───────────────────────────
                while True:
                    if await request.is_disconnected():
                        prod_task.cancel()
                        return

                    try:
                        event = await asyncio.wait_for(inner_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue

                    if event is None:  # 라운드 종료 신호
                        break

                    yield _sse(event)

                    if event.get("type") == "is_final":
                        return

                # ── 학생 입력 대기 ─────────────────────────
                if got_final:
                    return

                if got_waiting:
                    ch.waiting_for_user = True
                    try:
                        # 최대 5분 대기
                        item = await asyncio.wait_for(ch.queue.get(), timeout=300)
                    except asyncio.TimeoutError:
                        yield _sse({"type": "error", "code": "input_timeout", "message": "입력 대기 시간 초과"})
                        return
                    finally:
                        ch.waiting_for_user = False

                    # 학생 발화는 turns 엔드포인트에서 이미 DB에 저장했으므로
                    # user_content 를 빈 문자열로 전달해 중복 저장 방지
                    user_content = ""
                    continue

                # waiting 이벤트도 is_final 도 없으면 루프 종료
                break

        finally:
            if hb_task:
                hb_task.cancel()
            remove_channel(session_id)
            logger.debug("GET SSE 채널 정리: session_id=%s", session_id)

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  POST — 기존 호환 fetch 기반 SSE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/sessions/{session_id}/discussion")
async def discussion_sse_post(
    session_id: str,
    body: DiscussionRequest,
    request: Request,
    student_id: str = Depends(get_current_student),
):
    """
    fetch 기반 SSE (Authorization 헤더 지원).
    기존 클라이언트 호환 유지.
    """
    session_data = _validate_session(session_id, student_id)
    context = _build_context(student_id, session_id, session_data["passage_id"])

    async def generate():
        try:
            async for event in run_discussion(
                session_id=session_id,
                user_content=body.content,
                context=context,
                demo_mode=body.demo_mode,
            ):
                if await request.is_disconnected():
                    logger.info("POST SSE disconnect: session_id=%s", session_id)
                    return
                yield _sse(event)
        except Exception:
            logger.exception("POST SSE 실패: session_id=%s", session_id)
            yield _error("llm_failure", "토의 생성 중 오류가 발생했습니다.")

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)
