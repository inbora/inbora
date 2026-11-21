"""Super-admin: run the business.

- Businesses: plan, usage, channels, status; change plan, bonus
  conversations, suspend.
- Plans: create, edit, hide, reorder. A business keeps the limits it
  subscribed with (snapshot), so edits apply to new subscribers only.
- Plan requests, errors, and data-deletion requests."""
import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import billing, db, media, usage
from ..auth import CurrentUser, super_admin

router = APIRouter(prefix="/admin")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Overview: businesses, plans, plan requests

@router.get("/overview")
def overview(_: CurrentUser = Depends(super_admin)):
    # Custom plans made for one business aren't listed (the business row shows them).
    plans = db.select("plans", {"select": "*", "code": "not.like.custom-*", "order": "sort_order.asc,created_at.asc"})
    tenants = db.select("tenants", {
        "select": "id,name,slug,status,created_at,"
                  "subscriptions(status,limits,plan_id,period_start),"
                  "usage_counters(period_start,conversations_used,bonus_conversations),"
                  "channels(type,status,display_name),tenant_members(user_id)",
        "order": "created_at.desc",
        "limit": "500",
    })
    rows = []
    for t in tenants:
        active = next((s for s in t.get("subscriptions") or [] if s["status"] == "active"), None) or {}
        limits = active.get("limits") or {}
        counters = sorted(t.get("usage_counters") or [], key=lambda u: u["period_start"], reverse=True)
        u = counters[0] if counters else {}             # the current period's counter
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
            "bonus": int(u.get("bonus_conversations") or 0),
            "channels": sorted({c["type"] for c in t.get("channels") or [] if c["status"] == "connected"}),
            "broken": sorted({c["type"] for c in t.get("channels") or [] if c["status"] == "error"}),
            "members": len(t.get("tenant_members") or []),
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
    custom = [{**billing.custom_view(c), "tenant_id": c["tenant_id"], "tenant": (c.get("tenants") or {}).get("name"),
               "current": current.get(c["tenant_id"])}
              for c in db.select("custom_requests", {
                  "select": "id,tenant_id,status,conversations,kb_chars,seats,notes,offer_price,offer_sent_at,"
                            "offer_expires_at,created_at,tenants(name)",
                  "status": "in.(open,offered)", "order": "created_at.asc"})]
    open_errors = db.select("error_events", {"select": "id", "limit": "100"})
    open_deletions = db.select("deletion_requests", {"select": "id", "status": "eq.open"})
    return {"plans": plans, "tenants": rows, "requests": requests, "custom": custom,
            "counts": {"errors": len(open_errors), "deletions": len(open_deletions)}}


# ── Businesses

class PlanChange(BaseModel):
    plan_id: str = Field(max_length=40)


def _tenant(tenant_id: str) -> dict:
    t = db.select_one("tenants", {"select": "id,name,status", "id": f"eq.{tenant_id}"})
    if t is None:
        raise HTTPException(404, "Business not found")
    return t


@router.post("/tenants/{tenant_id}/plan")
def change_plan(tenant_id: str, body: PlanChange, _: CurrentUser = Depends(super_admin)):
    """Put a business on a plan: a new subscription with this plan's current
    limits and a fresh conversation count (also closes its open request)."""
    _tenant(tenant_id)
    plan = db.select_one("plans", {"select": "id,active", "id": f"eq.{body.plan_id}"})
    if plan is None:
        raise HTTPException(404, "Plan not found")
    if not plan["active"]:
        raise HTTPException(422, detail={"code": "plan_retired"})
    billing.subscribe(tenant_id, body.plan_id, "manual")
    return {"ok": True}


class Bonus(BaseModel):
    amount: int = Field(ge=-100000, le=100000)


@router.post("/tenants/{tenant_id}/bonus")
def add_bonus(tenant_id: str, body: Bonus, _: CurrentUser = Depends(super_admin)):
    """Extra conversations for the current period (a negative amount takes
    some back). If the business was at its limit, the agent answers again."""
    _tenant(tenant_id)
    cur = usage.current(tenant_id)
    if cur.get("status") != "ok":
        raise HTTPException(409, detail={"code": "no_plan"})
    row = db.select_one("usage_counters", {"select": "bonus_conversations,conversations_used",
                                           "tenant_id": f"eq.{tenant_id}", "period_start": f"eq.{cur['period_start']}"}) or {}
    bonus = max(0, int(row.get("bonus_conversations") or 0) + body.amount)
    quota = int(cur["quota"]) - int(row.get("bonus_conversations") or 0) + bonus
    values: dict = {"bonus_conversations": bonus}
    used = int(row.get("conversations_used") or 0)
    if used < quota:
        values["alert_100_at"] = None                   # the next "limit reached" alert can go out again
    if used * 5 < quota * 4:
        values["alert_80_at"] = None
    db.update("usage_counters", {"tenant_id": f"eq.{tenant_id}", "period_start": f"eq.{cur['period_start']}"}, values)
    return {"bonus": bonus, "quota": quota, "used": used}


class StatusChange(BaseModel):
    status: Literal["active", "suspended"]


@router.post("/tenants/{tenant_id}/status")
def set_status(tenant_id: str, body: StatusChange, _: CurrentUser = Depends(super_admin)):
    """Suspend: the team can't use the panel, the website chat goes off and
    the agent stops answering. Messages that arrive are still kept."""
    _tenant(tenant_id)
    db.update("tenants", {"id": f"eq.{tenant_id}"}, {"status": body.status})
    return {"status": body.status}


# ── Plans

class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    price_usd: float = Field(ge=0, le=100000)
    billing_period: Literal["monthly", "one_time", "trial"] = "monthly"
    trial_days: int | None = Field(default=None, ge=1, le=90)
    conversation_quota: int = Field(ge=0, le=10_000_000)
    max_channels: int = Field(ge=1, le=20)
    kb_char_limit: int = Field(ge=1000, le=5_000_000)
    seats: int = Field(ge=1, le=1000)
    show_branding: bool = True
    is_public: bool = True
    active: bool = True


class PlanCreate(PlanIn):
    code: str = Field(min_length=2, max_length=40)


@router.post("/plans")
def create_plan(body: PlanCreate, _: CurrentUser = Depends(super_admin)):
    code = body.code.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", code):
        raise HTTPException(422, detail={"code": "bad_code"})
    if db.select_one("plans", {"select": "id", "code": f"eq.{code}"}):
        raise HTTPException(409, detail={"code": "code_taken"})
    last = db.select_one("plans", {"select": "sort_order", "order": "sort_order.desc", "limit": "1"}) or {}
    return db.insert("plans", {**body.model_dump(), "code": code,
                               "sort_order": int(last.get("sort_order") or 0) + 1})[0]


class PlanEdit(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    price_usd: float | None = Field(default=None, ge=0, le=100000)
    billing_period: Literal["monthly", "one_time", "trial"] | None = None
    trial_days: int | None = Field(default=None, ge=1, le=90)
    conversation_quota: int | None = Field(default=None, ge=0, le=10_000_000)
    max_channels: int | None = Field(default=None, ge=1, le=20)
    kb_char_limit: int | None = Field(default=None, ge=1000, le=5_000_000)
    seats: int | None = Field(default=None, ge=1, le=1000)
    show_branding: bool | None = None
    is_public: bool | None = None
    active: bool | None = None
    is_signup_default: bool | None = None


@router.put("/plans/{plan_id}")
def edit_plan(plan_id: str, body: PlanEdit, _: CurrentUser = Depends(super_admin)):
    """Change a plan. Businesses already on it keep what they subscribed with;
    new subscribers (and plan changes) get the new terms."""
    plan = db.select_one("plans", {"select": "*", "id": f"eq.{plan_id}"})
    if plan is None:
        raise HTTPException(404, "Plan not found")
    values = body.model_dump(exclude_none=True)
    default = values.get("is_signup_default", plan["is_signup_default"])
    if default and (values.get("active") is False):
        raise HTTPException(422, detail={"code": "signup_default"})   # new businesses need an active plan
    if plan["is_signup_default"] and values.get("is_signup_default") is False:
        raise HTTPException(422, detail={"code": "signup_default"})   # pick another default instead
    if values.get("is_signup_default"):
        db.update("plans", {"is_signup_default": "eq.true", "id": f"neq.{plan_id}"}, {"is_signup_default": False})
    if not values:
        return plan
    return db.update("plans", {"id": f"eq.{plan_id}"}, {**values, "updated_at": _now()})[0]


class PlanOrder(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)


@router.post("/plans/order")
def reorder_plans(body: PlanOrder, _: CurrentUser = Depends(super_admin)):
    """The order plans appear in, on the Plan page and here."""
    for i, pid in enumerate(body.ids):
        db.update("plans", {"id": f"eq.{pid}"}, {"sort_order": i})
    return {"ok": True}


# ── Plan requests

@router.post("/requests/{request_id}/dismiss")
def dismiss_request(request_id: str, _: CurrentUser = Depends(super_admin)):
    db.update("upgrade_requests", {"id": f"eq.{request_id}", "status": "eq.open"},
              {"status": "dismissed", "resolved_at": _now()})
    return {"ok": True}


# ── Custom plan requests

class Offer(BaseModel):
    price_usd: float = Field(gt=0, le=100000)


@router.post("/custom/{request_id}/offer")
def send_offer(request_id: str, body: Offer, _: CurrentUser = Depends(super_admin)):
    """Send the business a price; it can accept from its Plan page for 14 days."""
    return billing.custom_view(billing.send_offer(request_id, body.price_usd))


@router.post("/custom/{request_id}/dismiss")
def dismiss_custom(request_id: str, _: CurrentUser = Depends(super_admin)):
    db.update("custom_requests", {"id": f"eq.{request_id}", "status": "in.(open,offered)"},
              {"status": "dismissed", "resolved_at": _now()})
    return {"ok": True}


# ── Errors

@router.get("/errors")
def list_errors(_: CurrentUser = Depends(super_admin)):
    rows = db.select("error_events", {"select": "id,kind,where_,message,detail,count,first_at,last_at,tenants(name)",
                                      "order": "last_at.desc", "limit": "100"})
    return [{**{k: v for k, v in r.items() if k not in ("tenants", "where_")}, "where": r["where_"],
             "business": (r.get("tenants") or {}).get("name")} for r in rows]


@router.delete("/errors/{error_id}")
def resolve_error(error_id: int, _: CurrentUser = Depends(super_admin)):
    """Mark as fixed (it comes back, with a new email, if it happens again)."""
    db.delete("error_events", {"id": f"eq.{error_id}"})
    return {"ok": True}


@router.delete("/errors")
def resolve_all_errors(_: CurrentUser = Depends(super_admin)):
    db.delete("error_events", {"id": "gt.0"})
    return {"ok": True}


# ── Data-deletion requests

def _matching_contacts(contact: str) -> list[dict]:
    """Contacts in any business that match an email, phone or username."""
    value = contact.strip()
    found: dict[str, dict] = {}
    select = "id,tenant_id,name,email,phone,username,external_id,tenants(name)"

    def add(rows):
        for r in rows:
            found[r["id"]] = r

    if "@" in value and "." in value.split("@")[-1] and not value.startswith("@"):
        email = value.lower()
        add(db.select("contacts", {"select": select, "email": f"eq.{email}"}))
        add(db.select("contacts", {"select": select, "external_id": f"eq.{email}"}))
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 7 and len(digits) >= len(value.replace(" ", "").replace("-", "")) - 2:
        tail = digits[-9:]                       # the number without its country code
        add(db.select("contacts", {"select": select, "phone": f"like.*{tail}"}))
        add(db.select("contacts", {"select": select, "external_id": f"like.*{tail}"}))
    username = value.lstrip("@").lower()
    if re.fullmatch(r"[a-z0-9._]{2,40}", username):
        add(db.select("contacts", {"select": select, "username": f"ilike.{username}"}))
    return list(found.values())


@router.get("/deletion-requests")
def list_deletions(_: CurrentUser = Depends(super_admin)):
    rows = db.select("deletion_requests", {"select": "*", "order": "created_at.desc", "limit": "100"})
    out = []
    for r in rows:
        matches = _matching_contacts(r["contact"]) if r["status"] == "open" else []
        out.append({**r, "matches": [{"business": (m.get("tenants") or {}).get("name"),
                                      "name": m.get("name"),
                                      "handle": m.get("email") or m.get("phone") or m.get("username") or m.get("external_id")}
                                     for m in matches]})
    return out


@router.post("/deletion-requests/{request_id}/delete-data")
def delete_data(request_id: str, _: CurrentUser = Depends(super_admin)):
    """Delete every matching customer, their conversations, messages and photos,
    in every business. Can't be undone."""
    req = db.select_one("deletion_requests", {"select": "*", "id": f"eq.{request_id}"})
    if req is None:
        raise HTTPException(404, "Request not found")
    matches = _matching_contacts(req["contact"])
    ids = [m["id"] for m in matches]
    photos: list[str] = []
    if ids:
        threads = db.select("threads", {"select": "id", "contact_id": f"in.({','.join(ids)})"})
        if threads:
            photos = [m["attachment_url"] for m in db.select("messages", {
                "select": "attachment_url", "thread_id": f"in.({','.join(t['id'] for t in threads)})",
                "attachment_url": "not.is.null"})]
        db.delete("contacts", {"id": f"in.({','.join(ids)})"})       # threads and messages go with them
    media.delete_urls(photos)
    db.update("deletion_requests", {"id": f"eq.{request_id}"},
              {"status": "done", "deleted_count": len(ids), "resolved_at": _now()})
    return {"deleted": len(ids)}


@router.post("/deletion-requests/{request_id}/dismiss")
def dismiss_deletion(request_id: str, _: CurrentUser = Depends(super_admin)):
    db.update("deletion_requests", {"id": f"eq.{request_id}", "status": "eq.open"},
              {"status": "dismissed", "resolved_at": _now()})
    return {"ok": True}
