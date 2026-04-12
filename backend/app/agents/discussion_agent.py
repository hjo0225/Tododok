"""토의 에이전트.

각 캐릭터의 시스템 프롬프트는 backend/prompts/*.md 에서 로드한다.
student_name 등 런타임 변수는 .format() 으로 주입된다.
"""
from __future__ import annotations

import logging
from pathlib import Path

from openai import OpenAI

from app.core.config import settings
from app.schemas.llm import DiscussionMessage

logger = logging.getLogger("uvicorn.error")

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_DIFFICULTY_VOCAB = {1: "초3~4 수준 어휘", 2: "초5~6 수준 어휘", 3: "중1 수준 어휘"}


# ────────────────────────────────────────────────────────────────
# 프롬프트 파일 로더
# ────────────────────────────────────────────────────────────────

def _load_prompt(name: str, **kwargs: str) -> str:
    """prompts/{name}.md 를 읽어 kwargs 변수를 치환해 반환."""
    path = _PROMPTS_DIR / f"{name}.md"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error("Prompt file not found: %s", path)
        raise
    for key, value in kwargs.items():
        raw = raw.replace(f"{{{key}}}", value)
    return raw


# Public alias — discussion.py 등 외부에서 import 가능
load_prompt = _load_prompt


# ────────────────────────────────────────────────────────────────
# 컨텍스트 빌더
# ────────────────────────────────────────────────────────────────

def _build_context_text(context: dict) -> str:
    lines = [
        f"[지문]\n{context['passage_content']}",
        "\n[객관식 결과]",
    ]
    for qr in context.get("question_results", []):
        lines.append(f"- {qr['question_type']} 유형: {'정답' if qr['is_correct'] else '오답'}")
    lines.append(f"\n전체 정답 여부: {'모두 정답' if context['all_correct'] else '오답 있음'}")
    lines.append(f"학생 수준: {_DIFFICULTY_VOCAB.get(context['student_level'], '중')}")
    if context.get("weak_areas"):
        lines.append(f"취약 영역: {', '.join(context['weak_areas'])}")
    return "\n".join(lines)


def _build_history_text(messages: list[dict], student_name: str) -> str:
    if not messages:
        return "(대화 없음)"
    speaker_map = {
        "moderator": "선생님(모더레이터)",
        "peer_a": "민지",
        "peer_b": "준서",
        "user": f"{student_name}(학생)",
    }
    return "\n".join(
        f"{speaker_map.get(m['speaker'], m['speaker'])}: {m['content']}"
        for m in messages
    )


# ────────────────────────────────────────────────────────────────
# Few-shot 예시 (모더레이터 5쌍 — gpt-4o-mini는 few-shot에 특히 잘 반응)
# ────────────────────────────────────────────────────────────────

def _few_shots_moderator(student_name: str) -> list[dict]:
    """모더레이터 few-shot 5쌍 (user/assistant 페어)."""
    return [
        # 1. 주제 1 오프닝 — 민지에게 첫 질문
        {"role": "user", "content": (
            "[주제 1/3 시작 | 대화 없음 | 지문: 운석은 태양계 형성 당시 생긴 조각, 과학자들이 연구 중]\n"
            "지시: 첫 번째 주제를 소개하고 민지에게 먼저 의견을 물으세요."
        )},
        {"role": "assistant", "content": (
            '{"content": "오늘 지문에서 운석을 연구하면 태양계의 비밀을 알 수 있다고 했는데요, '
            f'이게 왜 중요한지 함께 이야기해볼까요? 민지는 어떻게 생각하나요?"}}'
        )},
        # 2. 주제 1 — 민지·준서 발언 후 학생 차례
        {"role": "user", "content": (
            f"[주제 1/3 | 민지: '태양계 형성 과정을 알 수 있어요' | 준서: '잘 모르겠어요' | {student_name} 차례]\n"
            f"지시: 두 친구 의견을 언급하며 {student_name}에게 물으세요."
        )},
        {"role": "assistant", "content": (
            f'{{"content": "민지는 태양계가 만들어진 과정을 알 수 있다고 했고, 준서는 아직 잘 모르겠다고 했네요. '
            f'{student_name}는 두 친구 중 어느 쪽 생각이 더 와닿나요?"}}'
        )},
        # 3. 주제 2로 전환 — 학생 발언 후 민지에게
        {"role": "user", "content": (
            f"[주제 2/3 시작 | {student_name} 발언 후]\n"
            "지시: 자연스럽게 두 번째 주제로 넘어가며 민지에게 물으세요."
        )},
        {"role": "assistant", "content": (
            f'{{"content": "{student_name}가 좋은 생각을 나눠줬어요! 그럼 이번엔 조금 더 깊이 들어가서, '
            "글에서 '유성'과 '운석'이라는 단어가 어떻게 다르게 쓰였는지 이야기해볼까요? 민지는 어떻게 읽었나요?\"}}"
        )},
        # 4. 주제 2 심화 — 의견 차이 활용
        {"role": "user", "content": (
            "[주제 2/3 | 민지: '생명체 흔적이 중요해요' | 준서: '그냥 돌이랑 다를 게 없어요']\n"
            f"지시: 의견 차이를 언급하며 {student_name}에게 심화 질문을 하세요."
        )},
        {"role": "assistant", "content": (
            f'{{"content": "민지는 생명체 흔적이 중요하다고 했고, 준서는 그냥 돌과 다를 게 없는 것 같다고 했네요. '
            f'{student_name}는 어느 쪽이 더 설득력 있다고 느끼나요?"}}'
        )},
        # 5. 주제 3 — 마지막 주제 소개
        {"role": "user", "content": (
            "[주제 3/3 시작 | 마지막 주제]\n"
            "지시: 마지막 주제임을 자연스럽게 알리고 민지에게 먼저 물으세요."
        )},
        {"role": "assistant", "content": (
            '{"content": "오늘의 마지막 주제예요! 지금까지 운석의 과학적 의미에 대해 이야기했는데, '
            "이런 우주 연구가 우리 일상생활과 어떤 관계가 있을지 생각해볼까요? 민지는 어떻게 생각해요?\"}}"
        )},
    ]


# ────────────────────────────────────────────────────────────────
# OpenAI 호출 헬퍼
# ────────────────────────────────────────────────────────────────

def _call_openai(
    system: str,
    user_prompt: str,
    few_shots: list[dict] | None = None,
) -> str:
    """
    시스템 → few-shot 예시 → 실제 user 메시지 순으로 전달.
    client.beta.chat.completions.parse로 DiscussionMessage 스키마 강제.
    """
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    messages: list[dict] = [{"role": "system", "content": system}]
    if few_shots:
        messages.extend(few_shots)
    messages.append({"role": "user", "content": user_prompt})

    completion = client.beta.chat.completions.parse(
        model=settings.AGENT_MODEL,
        response_format=DiscussionMessage,
        messages=messages,
        temperature=0.85,
        max_tokens=300,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError("empty structured output")
    return parsed.content


# ────────────────────────────────────────────────────────────────
# 모더레이터 — 마무리 발언
# ────────────────────────────────────────────────────────────────

def call_moderator_close(context: dict, messages: list[dict]) -> str:
    student_name = context.get("student_name", "학생")
    ctx_text = _build_context_text(context)
    history = _build_history_text(messages, student_name)
    system = _load_prompt("moderator", student_name=student_name)
    user_prompt = (
        f"{ctx_text}\n\n[대화 이력]\n{history}\n\n"
        "3가지 주제 토의가 모두 끝났습니다. 선생님으로서 존댓말로 토의를 마무리해 주세요. "
        "오늘 나온 학생들의 다양한 의견을 간단히 언급하며, 수고했다는 따뜻한 격려로 마무리하세요. "
        "2~3문장으로 작성하세요."
    )
    return _call_openai(system, user_prompt, few_shots=_few_shots_moderator(student_name))
