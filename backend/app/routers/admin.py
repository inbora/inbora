"""Super-admin endpoints: plans and businesses at a glance, plan requests,
and changing a business's plan. Editing plans and the rest of tenant
management arrive in Step 8."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import billing, db
from ..auth import CurrentUser, super_admin

router = APIRouter(prefix="/admin")


@router.get("/overview")
def overview(_: CurrentUser = Depends(super_admin)):
    plans = db.select("plans", {"select": "*", "order": "sort_order.asc"})
    tenants = db.select("tenants", {
        "select": "id,name,slug,status,created_at,"
                  "subscriptions(status,limits,plan_id,period_start),"
                  "usage_counters(period_start,conversations_used,bonus_conversations)",
        "order": "created_at.desc",
        "limit": "200",
    })
    rows = []
    for t in tenants:
        active = next((s for s in t.get("subscriptions") or [] if s["status"] == "active"), None) or {}
        limits = active.get("limits") or {}
        counters = sorted(t.get("usage_counters") or [], key=lambda u: u["period_start"], reverse=True)
        # the counter of the current subscription period (latest one)
        u = counters[0] if counters else {}
        rows.append({
            "id": t["id"],
            "name": t["name"],
            "slug": t["slug"],
            "status": t["status"],
            "created_at": t["created_at"],
            "plan": limits.get("plan_name"),
            "plan_id": active.get("plan_id"),
            "used": int(u.get("conversations_used") or 0),
            "quota": int(limits.get("conversation_quota") or 0) + int(u.get("bonus_conversations") or 0),
        })
    reqs = db.select("upgrade_requests", {
        "select": "id,tenant_id,plan_id,created_at,tenants(name),plans(name)",
        "status": "eq.open", "order": "created_at.asc",
    })
    current = {r["id"]: r["plan"] for r in rows}
    requests = [{
        "id": r["id"], "tenant_id": r["tenant_id"], "tenant": (r.get("tenants") or {}).get("name"),
        "plan_id": r["plan_id"], "plan": (r.get("plans") or {}).get("name"),
        "current": current.get(r["tenant_id"]), "created_at": r["created_at"],
    } for r in reqs]
    return {"plans": plans, "tenants": rows, "requests": requests}


class PlanChange(BaseModel):
    plan_id: str = Field(max_length=40)


@router.post("/tenants/{tenant_id}/plan")
def change_plan(tenant_id: str, body: PlanChange, _: CurrentUser = Depends(super_admin)):
    """Put a business on a plan: a new subscription with this plan's current
    limits and a fresh conversation count (also closes its open request)."""
    if not db.select_one("tenants", {"select": "id", "id": f"eq.{tenant_id}"}):
        raise HTTPException(404, "Business not found")
    if not db.select_one("plans", {"select": "id", "id": f"eq.{body.plan_id}"}):
        raise HTTPException(404, "Plan not found")
    billing.subscribe(tenant_id, body.plan_id, "manual")
    return {"ok": True}


@router.post("/requests/{request_id}/dismiss")
def dismiss_request(request_id: str, _: CurrentUser = Depends(super_admin)):
    db.update("upgrade_requests", {"id": f"eq.{request_id}", "status": "eq.open"},
              {"status": "dismissed", "resolved_at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True}
