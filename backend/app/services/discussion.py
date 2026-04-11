"""
Discussion Orchestrator — Director Loop
P4: 토론의 심장. Director가 상태를 보고 다음 발화자를 결정하는 메인 루프.

구조:
  DiscussionState  — 토론 진행 상태 (라운드, 발화 순서, 이력)
  DirectorDecision — Director의 다음 행동 결정
  Director         — 상태 → 결정 (rule-based, P5에서 LLM으로 교체 가능)
  stream_agent_turn — 에이전트 LLM 호출 → 큐로 이벤트 push
  run_discussion   — 메인 async generator 루프
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncGenerator, Literal

from app.agents.discussion_agent import (
    call_moderator,
    call_moderator_close,
    call_peer_a,
    call_peer_b,
)
from app.core.constants import MAX_DISCUSSION_TOPICS
from app.core.supabase import supabase

logger = logging.getLogger("uvicorn.error")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  State
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class TurnRecord:
    speaker: str
    content: str
    round: int
    role: str = "assistant"


@dataclass
class DiscussionState:
    """
    토론 진행 상태. 매 요청마다 DB 메시지 이력에서 재구성된다.

    round            : 현재 토픽 번호 (1~MAX_DISCUSSION_TOPICS). 초과하면 마무리.
    round_turn_index : 라운드 내 위치
                       0=사회자 차례, 1=민지 차례, 2=준서 차례, 3=학생 차례
    demo_mode        : True이면 학생 턴을 건너뛰고 AI 3명이 자가 진행.
    """

    session_id: str
    context: dict
    history: list[TurnRecord] = field(default_factory=list)
    round: int = 1
    round_turn_index: int = 0
    is_final: bool = False
    demo_mode: bool = False

    @classmethod
    def from_db_messages(
        cls,
        session_id: str,
        context: dict,
        messages: list[dict],
        demo_mode: bool = False,
    ) -> DiscussionState:
        if not messages:
            return cls(session_id=session_id, context=context, demo_mode=demo_mode)

        history = [
            TurnRecord(
                speaker=m["speaker"],
                content=m["content"],
                round=m["round"],
                role=m.get("role", "assistant"),
            )
            for m in messages
        ]

        max_round = max(t.round for t in history)
        speakers_in_max_round = {t.speaker for t in history if t.round == max_round}

        if "user" in speakers_in_max_round:
            # 학생이 이미 발화했으면 다음 라운드 시작
            return cls(
                session_id=session_id,
                context=context,
                history=history,
                round=max_round + 1,
                round_turn_index=0,
                demo_mode=demo_mode,
            )

        # 이번 라운드에서 누가 발화했는지로 turn_index 계산
        turn_index = 0
        if "moderator" in speakers_in_max_round:
            turn_index = max(turn_index, 1)
        if "peer_a" in speakers_in_max_round:
            turn_index = max(turn_index, 2)
        if "peer_b" in speakers_in_max_round:
            turn_index = max(turn_index, 3)

        return cls(
            session_id=session_id,
            context=context,
            history=history,
            round=max_round,
            round_turn_index=turn_index,
            demo_mode=demo_mode,
        )

    def history_as_dicts(self) -> list[dict]:
        return [
            {"speaker": t.speaker, "content": t.content, "round": t.round, "role": t.role}
            for t in self.history
        ]

    def record_ai_turn(self, speaker: str, content: str) -> None:
        self.history.append(TurnRecord(speaker=speaker, content=content, round=self.round))
        self.round_turn_index += 1

    def advance_round(self) -> None:
        """학생 발화 처리 완료 후(혹은 데모 모드 스킵 후) 다음 라운드로."""
        self.round += 1
        self.round_turn_index = 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Director
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_NextSpeaker = Literal["moderator", "peer_a", "peer_b", "wait_for_user", "close", "_advance_round"]


@dataclass
class DirectorDecision:
    """Director가 내린 다음 행동 결정."""

    next_speaker: _NextSpeaker
    intent: str | None = None   # challenge/agree/ask_user/summarize/redirect/nudge
    target: str | None = None   # 응답 대상 발화자


# round_turn_index → (발화자, 의도)
_TURN_SEQUENCE: list[tuple[str, str]] = [
    ("moderator", "summarize"),
    ("peer_a", "challenge"),
    ("peer_b", "ask_user"),
]


class Director:
    """
    Rule-based Director (P4).
    상태를 보고 다음 발화자와 의도를 결정한다.

    P5 이후 LLM 기반 Director(claude-haiku)로 decide()를 교체할 수 있다.
    인터페이스: decide(state: DiscussionState) -> DirectorDecision
    """

    def decide(self, state: DiscussionState) -> DirectorDecision:
        # 라운드 초과 → 사회자 마무리 발언 후 종료
        if state.round > MAX_DISCUSSION_TOPICS:
            return DirectorDecision(next_speaker="close")

        idx = state.round_turn_index

        # 사회자/민지/준서 차례
        if idx < len(_TURN_SEQUENCE):
            speaker, intent = _TURN_SEQUENCE[idx]
            return DirectorDecision(
                next_speaker=speaker,  # type: ignore[arg-type]
                intent=intent,
                target="user",
            )

        # idx == 3: 학생 차례
        if state.demo_mode:
            # 자동 데모 모드: 학생 턴 건너뛰고 다음 라운드
            return DirectorDecision(next_speaker="_advance_round")

        return DirectorDecision(next_speaker="wait_for_user")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Agent Turn Streaming
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_AGENT_FN = {
    "moderator": call_moderator,
    "peer_a": call_peer_a,
    "peer_b": call_peer_b,
}


async def stream_agent_turn(
    speaker: str,
    state: DiscussionState,
    out_queue: asyncio.Queue,  # type: ignore[type-arg]
) -> str:
    """
    캐릭터별 LLM 호출 → 완성된 발화를 큐에 push → DB 저장.

    현재는 완성된 발화를 통째로 push한다(토큰 레벨 스트리밍은 추후 확장).
    반환값: 생성된 발화 텍스트.
    """
    agent_fn = _AGENT_FN[speaker]
    history_dicts = state.history_as_dicts()
    context = state.context
    topic_num = state.round

    loop = asyncio.get_event_loop()
    t0 = loop.time()
    content: str = await asyncio.to_thread(agent_fn, context, history_dicts, topic_num)
    latency_ms = int((loop.time() - t0) * 1000)

    _save_message(
        session_id=state.session_id,
        speaker=speaker,
        content=content,
        round_num=topic_num,
        role="assistant",
    )
    _log_llm_call(session_id=state.session_id, agent=speaker, latency_ms=latency_ms)

    event: dict = {"speaker": speaker, "content": content, "round": topic_num}
    await out_queue.put(event)
    return content


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Main Loop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def run_discussion(
    session_id: str,
    user_content: str,
    context: dict,
    demo_mode: bool = False,
) -> AsyncGenerator[dict, None]:
    """
    Director Loop 메인 루프. SSE 이벤트 dict를 yield한다.

    흐름:
      1. 학생 발화(user_content)가 있으면 DB에 저장
      2. DB 전체 이력에서 DiscussionState 재구성
      3. Director.decide(state) → 다음 행동 결정
      4. AI 발화 → yield 이벤트 / 학생 대기 → yield + return / 종료 → yield is_final
      5. demo_mode=True 이면 학생 턴 건너뛰고 3라운드 자가 완주
    """
    # ── 1. 학생 발화 저장 ─────────────────────────────────
    if user_content and user_content.strip():
        last_res = (
            supabase.table("messages")
            .select("round")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        user_round = last_res.data[0]["round"] if last_res.data else 1
        _save_message(
            session_id=session_id,
            speaker="user",
            content=user_content.strip(),
            round_num=user_round,
            role="user",
        )

    # ── 2. DB 이력에서 상태 재구성 ─────────────────────────
    msg_res = (
        supabase.table("messages")
        .select("speaker, content, round, role")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )
    state = DiscussionState.from_db_messages(
        session_id=session_id,
        context=context,
        messages=msg_res.data or [],
        demo_mode=demo_mode,
    )

    # ── 3. Director Loop ───────────────────────────────────
    director = Director()
    out_queue: asyncio.Queue = asyncio.Queue()

    while not state.is_final:
        decision = director.decide(state)

        # ── 학생 대기 ──────────────────────────────────────
        if decision.next_speaker == "wait_for_user":
            yield {"next_speaker": "user", "round": state.round, "is_final": False}
            return

        # ── 데모 모드: 학생 턴 건너뛰기 ────────────────────
        elif decision.next_speaker == "_advance_round":
            state.advance_round()
            continue

        # ── 종료: 사회자 마무리 발언 + is_final ─────────────
        elif decision.next_speaker == "close":
            loop = asyncio.get_event_loop()
            t0 = loop.time()
            close_content = await asyncio.to_thread(
                call_moderator_close, context, state.history_as_dicts()
            )
            latency_ms = int((loop.time() - t0) * 1000)

            _save_message(
                session_id=session_id,
                speaker="moderator",
                content=close_content,
                round_num=MAX_DISCUSSION_TOPICS,
                role="assistant",
            )
            _log_llm_call(session_id=session_id, agent="moderator_close", latency_ms=latency_ms)

            yield {"speaker": "moderator", "content": close_content, "round": MAX_DISCUSSION_TOPICS}
            yield {"is_final": True}
            state.is_final = True
            return

        # ── AI 에이전트 발화 ────────────────────────────────
        else:
            content = await stream_agent_turn(decision.next_speaker, state, out_queue)
            state.record_ai_turn(decision.next_speaker, content)
            yield out_queue.get_nowait()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DB Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _save_message(
    session_id: str,
    speaker: str,
    content: str,
    round_num: int,
    role: str,
) -> None:
    supabase.table("messages").insert({
        "session_id": session_id,
        "speaker": speaker,
        "content": content,
        "round": round_num,
        "role": role,
        "server_ts": datetime.now(timezone.utc).isoformat(),
    }).execute()


def _log_llm_call(session_id: str, agent: str, latency_ms: int) -> None:
    """llm_calls 테이블에 LLM 호출 로그 기록. 실패해도 메인 흐름을 중단하지 않는다."""
    try:
        supabase.table("llm_calls").insert({
            "session_id": session_id,
            "agent": agent,
            "model": "gpt-4o-mini",
            "latency_ms": latency_ms,
        }).execute()
    except Exception:
        logger.warning("llm_calls 기록 실패: session_id=%s agent=%s", session_id, agent, exc_info=True)
