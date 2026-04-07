from typing import Any

from supabase import Client, create_client

from app.core.config import settings


def create_supabase(key: str) -> Client:
    if not settings.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is not configured")
    if not key:
        raise RuntimeError("Supabase key is not configured")
    return create_client(settings.SUPABASE_URL, key)


class LazySupabaseClient:
    def __init__(self, key: str) -> None:
        self._key = key
        self._client: Client | None = None

    def _get_client(self) -> Client:
        if self._client is None:
            self._client = create_supabase(self._key)
        return self._client

    def __getattr__(self, item: str) -> Any:
        return getattr(self._get_client(), item)


supabase = LazySupabaseClient(settings.SUPABASE_SERVICE_ROLE_KEY)
supabase_anon = LazySupabaseClient(settings.SUPABASE_ANON_KEY)
