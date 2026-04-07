from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from app.core.constants import SESSION_TIMEOUT_MINUTES
from app.core.supabase import supabase

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/cleanup-sessions")
def cleanup_sessions():
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=SESSION_TIMEOUT_MINUTES)).isoformat()

    expired_res = (
        supabase.table("sessions")
        .select("id")
        .eq("status", "in_progress")
        .lt("started_at", cutoff)
        .execute()
    )
    expired_sessions = expired_res.data or []
    expired_ids = [row["id"] for row in expired_sessions if row.get("id")]

    if expired_ids:
        (
            supabase.table("sessions")
            .update({"status": "abandoned"})
            .in_("id", expired_ids)
            .execute()
        )

    return {
        "ok": True,
        "cutoff": cutoff,
        "abandoned_count": len(expired_ids),
    }
