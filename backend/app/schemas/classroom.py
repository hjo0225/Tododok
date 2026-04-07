from pydantic import BaseModel


class ClassroomCreate(BaseModel):
    name: str


class ClassroomCreateResponse(BaseModel):
    id: str
    join_code: str


class ClassroomItem(BaseModel):
    id: str
    name: str
    join_code: str
    student_count: int


class ScoreHistoryItem(BaseModel):
    date: str
    avg_score: float


class StudentDashboardItem(BaseModel):
    id: str
    name: str
    level: int
    teacher_override_level: int | None
    weak_areas: list[str]
    streak_count: int
    recent_avg: float | None
    needs_attention: bool
    score_history: list[ScoreHistoryItem]


class LevelOverrideRequest(BaseModel):
    level: int | None


class DashboardResponse(BaseModel):
    classroom_name: str
    students: list[StudentDashboardItem]
