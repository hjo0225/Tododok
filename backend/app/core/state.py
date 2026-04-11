"""
세션 채널 레지스트리 — P6 학생 입력 채널 지원.

각 세션에 대해 asyncio.Queue 하나를 유지한다.
SSE 생산자(GET /discussion)가 채널을 생성·삭제하고,
학생 입력(POST /discussion/turns)이 큐에 push한다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

__all__ = ["SessionChannel", "get_channel", "create_channel", "remove_channel"]


@dataclass
class SessionChannel:
    """세션 하나당 생성되는 양방향 채널."""

    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    waiting_for_user: bool = False


# 세션 ID → 채널 (서버 프로세스 메모리)
_channels: dict[str, SessionChannel] = {}


def get_channel(session_id: str) -> SessionChannel | None:
    return _channels.get(session_id)


def create_channel(session_id: str) -> SessionChannel:
    ch = SessionChannel()
    _channels[session_id] = ch
    return ch


def remove_channel(session_id: str) -> None:
    _channels.pop(session_id, None)
