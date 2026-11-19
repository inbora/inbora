"""Which business (tenant) the logged-in user belongs to."""
from fastapi import Depends, HTTPException

from . import db
from .auth import CurrentUser, current_user


def tenant_id_for(user_id: str) -> str | None:
    row = db.select_one("tenant_members", {
        "select": "tenant_id", "user_id": f"eq.{user_id}", "order": "created_at.asc",
    })
    return row["tenant_id"] if row else None


def current_tenant_id(user: CurrentUser = Depends(current_user)) -> str:
    tid = tenant_id_for(user.id)
    if tid is None:
        raise HTTPException(404, "No business found for this user")
    tenant = db.select_one("tenants", {"select": "status", "id": f"eq.{tid}"})
    if tenant and tenant["status"] == "suspended":
        raise HTTPException(403, "This business is suspended")
    return tid
