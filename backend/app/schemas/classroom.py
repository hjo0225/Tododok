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
