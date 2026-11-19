"""Super-admin endpoints. Step 1 is read-only; plan editing and tenant
management arrive in Step 8."""
from fastapi import APIRouter, Depends

from .. import db
from ..auth import CurrentUser, super_admin

router = APIRouter(prefix="/admin")


@router.get("/overview")
def overview(_: CurrentUser = Depends(super_admin)):
    plans = db.select("plans", {"select": "*", "order": "sort_order.asc"})
    tenants = db.select("tenants", {
        "select": "id,name,slug,status,created_at,subscriptions(status,limits)",
        "order": "created_at.desc",
        "limit": "200",
    })
    rows = []
    for t in tenants:
        active = next((s for s in t.get("subscriptions") or [] if s["status"] == "active"), None)
        rows.append({
            "id": t["id"],
            "name": t["name"],
            "slug": t["slug"],
            "status": t["status"],
            "created_at": t["created_at"],
            "plan": (active or {}).get("limits", {}).get("plan_name"),
        })
    return {"plans": plans, "tenants": rows}
