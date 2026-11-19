"""A small job queue in Postgres (the `jobs` table)."""
from datetime import datetime, timedelta, timezone
from typing import Any

from . import db

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = [5, 30]          # wait before attempt 2, attempt 3


def _at(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def enqueue(kind: str, tenant_id: str | None, payload: dict[str, Any], delay_seconds: float = 0) -> int:
    row = db.insert("jobs", {
        "kind": kind, "tenant_id": tenant_id, "payload": payload, "run_after": _at(delay_seconds),
    })
    return row[0]["id"]


def claim(limit: int = 5) -> list[dict[str, Any]]:
    return db.rpc("claim_jobs", {"p_limit": limit}) or []


def complete(job_id: int) -> None:
    db.update("jobs", {"id": f"eq.{job_id}"}, {"status": "done", "last_error": None})


def fail(job: dict[str, Any], error: str) -> bool:
    """Record a failure. Returns True if the job will be retried."""
    attempts = int(job.get("attempts") or 1)
    if attempts < MAX_ATTEMPTS:
        wait = BACKOFF_SECONDS[min(attempts - 1, len(BACKOFF_SECONDS) - 1)]
        db.update("jobs", {"id": f"eq.{job['id']}"},
                  {"status": "queued", "run_after": _at(wait), "last_error": error[:1000]})
        return True
    db.update("jobs", {"id": f"eq.{job['id']}"}, {"status": "failed", "last_error": error[:1000]})
    return False


def purge_finished(days: int = 7) -> None:
    db.delete("jobs", {"status": "in.(done,failed)", "created_at": f"lt.{_at(-days * 86400)}"})
