from pydantic import BaseModel, EmailStr, Field, field_validator


# --- Teacher Auth ---

class TeacherSignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name must not be empty")
        return stripped


class TeacherLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TeacherProfile(BaseModel):
    user_id: str
    email: str
    name: str


# --- Student Auth ---

class StudentSignUpRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    classroom_code: str


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


# --- Responses ---

class TeacherAuthResponse(BaseModel):
    user_id: str
    email: str
    name: str
    access_token: str
    refresh_token: str
    expires_in: int | None = None


class OkResponse(BaseModel):
    ok: bool = True
