from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from supabase import create_client

from app.core.config import settings
from app.schemas.auth import (
    OkResponse,
    TeacherLoginRequest,
    TeacherResendRequest,
    TeacherSignUpRequest,
    TeacherVerifyRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth/teacher", tags=["auth-teacher"])

RESEND_COOLDOWN_SECONDS = 60


def _client():
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


def _service_client():
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


@router.post("/signup", response_model=OkResponse, status_code=status.HTTP_201_CREATED)
def teacher_signup(body: TeacherSignUpRequest):
    client = _client()

    res = client.auth.sign_up({"email": body.email, "password": body.password})
    if res.user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SIGNUP_FAILED")

    user_id = res.user.id

    # teachers 테이블에 name INSERT (service role로 RLS 우회)
    service = _service_client()
    service.table("teachers").insert({"id": user_id, "name": body.name, "email": body.email}).execute()

    return OkResponse()


@router.post("/verify", response_model=TokenResponse)
def teacher_verify(body: TeacherVerifyRequest):
    client = _client()

    res = client.auth.verify_otp({"email": body.email, "token": body.token, "type": "signup"})
    if res.session is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_OR_EXPIRED_TOKEN")

    return TokenResponse(access_token=res.session.access_token)


@router.post("/resend", response_model=OkResponse)
def teacher_resend(body: TeacherResendRequest):
    service = _service_client()

    # 60초 쿨다운: teachers 테이블의 last_resend_at 확인
    row = service.table("teachers").select("last_resend_at").eq("email", body.email).maybe_single().execute()

    if row.data and row.data.get("last_resend_at"):
        last = datetime.fromisoformat(row.data["last_resend_at"].replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            retry_after = int(RESEND_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="RESEND_COOLDOWN",
                headers={"Retry-After": str(retry_after)},
            )

    client = _client()
    client.auth.resend({"type": "signup", "email": body.email})

    # last_resend_at 갱신
    now_iso = datetime.now(timezone.utc).isoformat()
    service.table("teachers").update({"last_resend_at": now_iso}).eq("email", body.email).execute()

    return OkResponse()


@router.post("/login", response_model=TokenResponse)
def teacher_login(body: TeacherLoginRequest):
    client = _client()

    res = client.auth.sign_in_with_password({"email": body.email, "password": body.password})
    if res.session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_CREDENTIALS")

    # 이메일 미인증 체크
    if res.user and res.user.email_confirmed_at is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="EMAIL_NOT_VERIFIED")

    return TokenResponse(access_token=res.session.access_token)
