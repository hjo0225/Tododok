from pydantic import BaseModel


class QuestionOut(BaseModel):
    index: int        # 1~3
    type: str         # "info" | "reasoning" | "vocabulary"
    text: str
    choices: list[str]  # 3개


class PassageOut(BaseModel):
    title: str
    genre: str
    difficulty: int
    content: str


class SessionStartResponse(BaseModel):
    session_id: str
    passage: PassageOut
    questions: list[QuestionOut]


class AnswerSubmitRequest(BaseModel):
    question_index: int   # 1~3
    selected_index: int   # 0~2


class AnswerSubmitResponse(BaseModel):
    ok: bool = True
