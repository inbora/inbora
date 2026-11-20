"""The business's plan: the plans it can move to, and asking for one."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import billing, db
from ..auth import CurrentUser, current_user
from ..tenancy import current_tenant_id

router = APIRouter(prefix="/billing")

PLAN_FIELDS = "id,code,name,price_usd,billing_period,conversation_quota,max_channels,kb_char_limit,seats,show_branding"


def _current_code(tenant_id: str) -> str | None:
    sub = db.select_one("subscriptions", {"select": "limits", "tenant_id": f"eq.{tenant_id}", "status": "eq.active"})
    return ((sub or {}).get("limits") or {}).get("plan_code")


@router.get("/plans")
def plans(tenant_id: str = Depends(current_tenant_id)):
    rows = db.select("plans", {"select": PLAN_FIELDS, "active": "eq.true", "is_public": "eq.true",
                               "order": "sort_order.asc"})
    req = db.select_one("upgrade_requests", {"select": "created_at,plans(code,name)", "tenant_id": f"eq.{tenant_id}",
                                             "status": "eq.open"})
    return {"plans": rows, "current": _current_code(tenant_id),
            "request": {"plan_code": req["plans"]["code"], "plan_name": req["plans"]["name"],
                        "created_at": req["created_at"]} if req and req.get("plans") else None}


class CheckoutIn(BaseModel):
    plan_code: str = Field(max_length=40)


@router.post("/checkout")
def checkout(body: CheckoutIn, user: CurrentUser = Depends(current_user),
             tenant_id: str = Depends(current_tenant_id)):
    """Ask for another plan. With the manual provider the super-admin is told
    and assigns it; a payment provider would return a checkout link."""
    plan = db.select_one("plans", {"select": PLAN_FIELDS, "code": f"eq.{body.plan_code}", "active": "eq.true",
                                   "is_public": "eq.true"})
    if plan is None:
        raise HTTPException(404, "Plan not found")
    if plan["code"] == _current_code(tenant_id):
        raise HTTPException(409, detail={"code": "current_plan"})
    return billing.provider().create_checkout(tenant_id, plan, user.id)


@router.delete("/request")
def cancel_request(tenant_id: str = Depends(current_tenant_id)):
    db.update("upgrade_requests", {"tenant_id": f"eq.{tenant_id}", "status": "eq.open"}, {"status": "dismissed"})
    return {"ok": True}


@router.post("/webhook/{provider_name}")
async def webhook(provider_name: str, request: Request):
    raw = await request.body()
    return billing.provider(provider_name).handle_webhook(raw, dict(request.headers))
