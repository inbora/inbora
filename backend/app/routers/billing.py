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
    pro = next((p for p in rows if p["code"] == "pro"), None) or (rows[-1] if rows else {})
    return {"plans": rows, "current": _current_code(tenant_id),
            "request": {"plan_code": req["plans"]["code"], "plan_name": req["plans"]["name"],
                        "created_at": req["created_at"]} if req and req.get("plans") else None,
            "channels_used": _channels_used(tenant_id),
            "custom": billing.custom_view(billing.open_custom(tenant_id)),
            # The Custom form starts from the biggest plan's values.
            "custom_defaults": {"conversations": pro.get("conversation_quota") or 2000,
                                "kb_chars": pro.get("kb_char_limit") or 100000, "seats": pro.get("seats") or 10}}


def _channels_used(tenant_id: str) -> int:
    return len(db.select("channels", {"select": "id", "tenant_id": f"eq.{tenant_id}", "status": "neq.disconnected"}))


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
    used = _channels_used(tenant_id)
    if used > int(plan["max_channels"]):
        # Fewer channels on that plan: disconnect some first.
        raise HTTPException(422, detail={"code": "channel_count", "limit": plan["max_channels"], "used": used})
    return billing.provider().create_checkout(tenant_id, plan, user.id)


@router.delete("/request")
def cancel_request(tenant_id: str = Depends(current_tenant_id)):
    db.update("upgrade_requests", {"tenant_id": f"eq.{tenant_id}", "status": "eq.open"}, {"status": "dismissed"})
    return {"ok": True}


@router.post("/webhook/{provider_name}")
async def webhook(provider_name: str, request: Request):
    raw = await request.body()
    return billing.provider(provider_name).handle_webhook(raw, dict(request.headers))


# ── Custom plan

class CustomIn(BaseModel):
    conversations: int = Field(ge=1, le=1_000_000)
    kb_chars: int = Field(ge=1000, le=5_000_000)
    seats: int = Field(ge=1, le=1000)
    notes: str = Field(default="", max_length=2000)


@router.post("/custom", status_code=201)
def request_custom(body: CustomIn, user: CurrentUser = Depends(current_user),
                   tenant_id: str = Depends(current_tenant_id)):
    """Ask for a Custom plan; the super-admin replies with a price."""
    row = billing.request_custom(tenant_id, user.id, body.conversations, body.kb_chars, body.seats, body.notes.strip())
    return {"custom": billing.custom_view(row)}


@router.delete("/custom")
def withdraw_custom(tenant_id: str = Depends(current_tenant_id)):
    db.update("custom_requests", {"tenant_id": f"eq.{tenant_id}", "status": "in.(open,offered)"}, {"status": "dismissed"})
    return {"ok": True}


@router.post("/custom/{request_id}/accept")
def accept_custom(request_id: str, tenant_id: str = Depends(current_tenant_id)):
    plan = billing.accept_offer(tenant_id, request_id)
    return {"ok": True, "plan": plan["name"]}
