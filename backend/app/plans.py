"""The plan limits a business is on (a snapshot taken when it subscribed)."""
from . import db


def limits(tenant_id: str) -> dict:
    sub = db.select_one("subscriptions", {
        "select": "limits", "tenant_id": f"eq.{tenant_id}", "status": "eq.active",
        "order": "created_at.desc", "limit": "1",
    })
    return (sub or {}).get("limits") or {}
