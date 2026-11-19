"""Thin Supabase (PostgREST) client using the service_role key.

The service_role key bypasses row-level security, so every query here must
filter by tenant explicitly. Never expose this key to the browser."""
from typing import Any

import httpx

from .config import get_settings

_client: httpx.Client | None = None


def _key_headers(key: str) -> dict[str, str]:
    """New Supabase secret keys (sb_secret_...) are not JWTs: they go in the
    `apikey` header only — sent as `Authorization: Bearer` they are rejected.
    Legacy service_role keys are JWTs (start with "eyJ") and go in both."""
    headers = {"apikey": key}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def client() -> httpx.Client:
    global _client
    if _client is None:
        s = get_settings()
        _client = httpx.Client(
            base_url=s.rest_url,
            headers={**_key_headers(s.supabase_service_role_key.strip()),
                     "Content-Type": "application/json"},
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


def check() -> tuple[bool, str]:
    """(ok, reason). The reason names what failed, without any secrets."""
    try:
        res = client().get("/plans", params={"select": "id", "limit": "1"})
    except httpx.HTTPError as e:
        return False, f"cannot connect to SUPABASE_URL ({type(e).__name__})"
    if res.status_code == 200:
        return True, "ok"
    try:
        body = res.json()
        msg = body.get("message") or body.get("msg") or body.get("error") or ""
        code = body.get("code") or ""
    except ValueError:
        msg, code = res.text[:120], ""
    hint = {
        401: "key rejected — check SUPABASE_SERVICE_ROLE_KEY",
        403: "key not allowed — use the secret / service_role key, not the anon key",
        404: "table not found — run 0001_init.sql, and check SUPABASE_URL has no extra path",
    }.get(res.status_code, "unexpected response")
    return False, f"HTTP {res.status_code} {code}: {hint} ({msg})".strip()


def ping() -> bool:
    """True if Supabase answers with this key."""
    return check()[0]
