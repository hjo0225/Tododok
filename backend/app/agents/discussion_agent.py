"""토의 에이전트.

각 캐릭터의 시스템 프롬프트는 backend/prompts/*.md 에서 로드한다.
student_name 등 런타임 변수는 .format() 으로 주입된다.
"""
from __future__ import annotations

import logging
from pathlib import Path

from openai import OpenAI

from app.core.config import settings
from app.schemas.llm import DiscussionMessage, DiscussionPlan

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
    if kwargs:
        raw = raw.format(**kwargs)
    return raw


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


def _last_message_by(messages: list[dict], speaker: str) -> str | None:
    for m in reversed(messages):
        if m.get("speaker") == speaker:
            return m["content"]
    return None


# ────────────────────────────────────────────────────────────────
# OpenAI 호출 헬퍼
# ────────────────────────────────────────────────────────────────

def _call_openai(system: str, user_prompt: str) -> str:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        response_format=DiscussionMessage,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.85,
        max_tokens=300,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError("empty structured output")
    return parsed.content


def _call_openai_plan(system: str, user_prompt: str) -> DiscussionPlan:
    """디렉터 전용: DiscussionPlan 구조화 출력."""
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        response_format=DiscussionPlan,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=400,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError("empty director plan output")
    return parsed


# ────────────────────────────────────────────────────────────────
# 디렉터 — 토의 주제 플랜 생성 (세션당 1회)
# ────────────────────────────────────────────────────────────────

def call_director(context: dict) -> DiscussionPlan:
    """지문·학생 데이터를 분석해 3개 토의 주제를 설계한다."""
    student_level = context.get("student_level", 2)
    ctx_text = _build_context_text(context)
    system = _load_prompt("director")
    user_prompt = (
        f"{ctx_text}\n\n"
        "위 지문과 학생 데이터를 바탕으로 3개의 토의 주제를 설계해 주세요. "
        f"학생 수준은 {_DIFFICULTY_VOCAB.get(student_level, '초5~6 수준 어휘')}입니다."
    )
    return _call_openai_plan(system, user_prompt)


# ────────────────────────────────────────────────────────────────
# 모더레이터
# ────────────────────────────────────────────────────────────────

def call_moderator(
    context: dict,
    messages: list[dict],
    topic_num: int,
    plan: DiscussionPlan | None = None,
) -> str:
    student_name = context.get("student_name", "학생")
    ctx_text = _build_context_text(context)
    history = _build_history_text(messages, student_name)
    system = _load_prompt("moderator", student_name=student_name)

    # 주제별 지시 — 디렉터 플랜이 있으면 우선 사용
    if plan:
        topic_text = {1: plan.topic_1, 2: plan.topic_2, 3: plan.topic_3}.get(topic_num, plan.topic_3)
        if topic_num == 1:
            instruction = f"아래 주제로 토의를 시작하고 민지에게 먼저 의견을 물어보세요.\n주제: {topic_text}"
        elif topic_num == 2:
            instruction = (
                f"{student_name}의 발언을 짧게 언급하며 자연스럽게 두 번째 주제로 넘어가세요. "
                f"주제: {topic_text} — 민지에게 먼저 의견을 물어보세요."
            )
        else:
            instruction = (
                f"이번이 마지막 주제임을 자연스럽게 알리고 아래 주제로 넘어가세요. "
                f"주제: {topic_text} — 민지에게 먼저 의견을 물어보세요."
            )
    else:
        # 폴백: 플랜 없을 때 기존 템플릿 사용
        if topic_num == 1:
            instruction = "지문에서 흥미로운 주제 1가지를 선정하여 첫 번째 토의 주제를 소개하고, 민지에게 먼저 의견을 물어보세요."
        elif topic_num == 2:
            instruction = (
                f"{student_name}의 발언을 짧게 언급하며 자연스럽게 두 번째 주제로 넘어가세요. "
                "민지와 준서의 의견 차이가 있었다면 그것을 언급하며 심화 질문을 던지고 민지에게 먼저 의견을 물어보세요."
            )
        else:
            instruction = (
                "두 번째 주제 토의를 마무리하고 세 번째 마지막 주제를 소개하세요. "
                "이번이 마지막 주제임을 자연스럽게 알리고, 민지에게 먼저 의견을 물어보세요."
            )

    user_prompt = (
        f"{ctx_text}\n\n[현재 주제]: {topic_num}번째 주제 (총 3개 주제)\n\n[대화 이력]\n{history}\n\n"
        f"선생님으로서 존댓말로 {instruction}"
    )
    return _call_openai(system, user_prompt)


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
    return _call_openai(system, user_prompt)


# ────────────────────────────────────────────────────────────────
# 또래 AI — 민지 (peer_a)
# ────────────────────────────────────────────────────────────────

def call_peer_a(context: dict, messages: list[dict], topic_num: int) -> str:
    student_name = context.get("student_name", "학생")
    ctx_text = _build_context_text(context)
    history = _build_history_text(messages, student_name)
    vocab_level = _DIFFICULTY_VOCAB.get(min(context["student_level"] + 1, 3), "중1 수준")
    system = _load_prompt("peer_a", student_name=student_name) + f"\n어휘 수준: {vocab_level}"

    last_peer_b = _last_message_by(messages, "peer_b")
    last_user = _last_message_by(messages, "user")

    reaction_instruction = ""
    if last_peer_b:
        reaction_instruction = (
            f"\n\n[준서의 직전 발언]: \"{last_peer_b}\"\n"
            "위 준서 발언에 반드시 직접 반응하며 시작하세요. "
            "동의한다면 이유를 더해 공감하고, 생각이 다르다면 '아, 나는 좀 다른데' 식으로 반론을 펼치세요."
        )
    elif last_user:
        reaction_instruction = (
            f"\n\n[{student_name}의 직전 발언]: \"{last_user}\"\n"
            f"{student_name}의 발언에 반응하며 시작하세요. 동의하거나 다른 시각을 제시하세요."
        )

    user_prompt = (
        f"{ctx_text}\n\n[현재 주제]: {topic_num}번째 주제\n\n[대화 이력]\n{history}"
        f"{reaction_instruction}\n\n"
        f"민지로서 위 지시에 따라 발언하세요. 선생님께는 존댓말, 친구({student_name}·준서)에게는 반말을 사용하세요."
    )
    return _call_openai(system, user_prompt)


# ────────────────────────────────────────────────────────────────
# 또래 AI — 준서 (peer_b)
# ────────────────────────────────────────────────────────────────

def call_peer_b(context: dict, messages: list[dict], topic_num: int) -> str:
    student_name = context.get("student_name", "학생")
    ctx_text = _build_context_text(context)
    history = _build_history_text(messages, student_name)
    vocab_level = _DIFFICULTY_VOCAB.get(context["student_level"], "초5~6 수준")
    system = _load_prompt("peer_b", student_name=student_name) + f"\n어휘 수준: {vocab_level}"

    last_peer_a = _last_message_by(messages, "peer_a")
    last_user = _last_message_by(messages, "user")

    if last_peer_a:
        reaction_instruction = (
            f"\n\n[민지의 직전 발언]: \"{last_peer_a}\"\n"
            "위 민지 발언에 반드시 직접 반응하며 시작하세요. "
            "동의한다면 '맞아, 나도~' 식으로, 생각이 다르다면 '민지야, 나는 좀 달라~' 식으로 반론을 펼치세요. "
            "절반 이상의 확률로 다른 관점을 제시하세요."
        )
    elif last_user:
        reaction_instruction = (
            f"\n\n[{student_name}의 직전 발언]: \"{last_user}\"\n"
            f"{student_name}의 발언에 반응하며 시작하세요."
        )
    else:
        reaction_instruction = ""

    user_prompt = (
        f"{ctx_text}\n\n[현재 주제]: {topic_num}번째 주제\n\n[대화 이력]\n{history}"
        f"{reaction_instruction}\n\n"
        f"준서로서 위 지시에 따라 발언하세요. 선생님께는 존댓말, 친구({student_name}·민지)에게는 반말을 사용하세요."
    )
    return _call_openai(system, user_prompt)
