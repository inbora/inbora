"""Thin Supabase (PostgREST) client using the service_role key.

The service_role key bypasses row-level security, so every query here must
filter by tenant explicitly. Never expose this key to the browser."""
from typing import Any

import httpx

from .config import get_settings

_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        s = get_settings()
        _client = httpx.Client(
            base_url=s.rest_url,
            headers={
                "apikey": s.supabase_service_role_key,
                "Authorization": f"Bearer {s.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
    return _client


def select(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    """GET /rest/v1/{table} with PostgREST query params,
    e.g. {"select": "*", "id": "eq.123"}."""
    res = client().get(f"/{table}", params=params)
    res.raise_for_status()
    return res.json()


def select_one(table: str, params: dict[str, str]) -> dict[str, Any] | None:
    rows = select(table, {**params, "limit": "1"})
    return rows[0] if rows else None


def ping() -> bool:
    """True if Supabase answers with this key."""
    try:
        res = client().get("/plans", params={"select": "id", "limit": "1"})
        return res.status_code == 200
    except httpx.HTTPError:
        return False
