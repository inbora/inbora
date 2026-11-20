"""The logged-in user, their business (tenant) and its plan."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, usage
from ..auth import CurrentUser, current_user

router = APIRouter()


@router.get("/me")
def me(user: CurrentUser = Depends(current_user)):
    membership = db.select_one("tenant_members", {
        "select": "role,tenants(id,name,slug,default_language,status)",
        "user_id": f"eq.{user.id}",
        "order": "created_at.asc",
    })
    if membership is None or membership.get("tenants") is None:
        raise HTTPException(404, "No business found for this user")
    tenant = membership["tenants"]

    cur = usage.current(tenant["id"])        # also moves a monthly plan into the current month
    sub = db.select_one("subscriptions", {
        "select": "limits,period_start,period_end,status",
        "tenant_id": f"eq.{tenant['id']}",
        "status": "eq.active",
    })

    if cur.get("status") != "ok":
        # Counting not available: show the last stored count.
        u = db.select_one("usage_counters", {
            "select": "conversations_used,bonus_conversations", "tenant_id": f"eq.{tenant['id']}",
            "order": "period_start.desc"}) or {}
        quota = int(((sub or {}).get("limits") or {}).get("conversation_quota") or 0)
        cur = {"used": u.get("conversations_used", 0), "quota": quota + int(u.get("bonus_conversations") or 0)}

    plan = None
    if sub:
        limits = sub["limits"]
        plan = {
            "code": limits.get("plan_code"),
            "name": limits.get("plan_name"),
            "billing_period": limits.get("billing_period"),
            "conversation_quota": int(cur.get("quota") or 0),
            "conversations_used": int(cur.get("used") or 0),
            "max_channels": limits.get("max_channels"),
            "kb_char_limit": limits.get("kb_char_limit"),
            "seats": limits.get("seats"),
            "show_branding": bool(limits.get("show_branding", True)),
            "period_end": sub["period_end"],
        }

    profile = db.select_one("profiles", {"select": "full_name", "id": f"eq.{user.id}"}) or {}
    broken = db.select("channels", {"select": "type,display_name", "tenant_id": f"eq.{tenant['id']}",
                                    "status": "eq.error"})
    return {
        "user": {"id": user.id, "email": user.email, "is_super_admin": user.is_super_admin,
                 "full_name": profile.get("full_name") or ""},
        "tenant": {**tenant, "role": membership["role"]},
        "plan": plan,
        "channel_alerts": broken,
    }


class ProfileIn(BaseModel):
    full_name: str = Field(default="", max_length=80)


@router.put("/me/profile")
def update_profile(body: ProfileIn, user: CurrentUser = Depends(current_user)):
    """The user's own name: shown on their replies in the inbox and used to sign AI drafts."""
    name = " ".join(body.full_name.split())
    db.update("profiles", {"id": f"eq.{user.id}"}, {"full_name": name or None})
    return {"full_name": name}


class BusinessIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    slug: str | None = Field(default=None, max_length=40)


_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")


@router.put("/me/business")
def update_business(body: BusinessIn, user: CurrentUser = Depends(current_user)):
    """The business name and ID. Owners and admins only."""
    m = db.select_one("tenant_members", {"select": "tenant_id,role", "user_id": f"eq.{user.id}",
                                         "order": "created_at.asc"})
    if m is None:
        raise HTTPException(404, "No business found for this user")
    if m["role"] not in ("owner", "admin"):
        raise HTTPException(403, "Only the owner or an admin can change this")
    tid, values = m["tenant_id"], {}
    if body.name is not None:
        values["name"] = " ".join(body.name.split())
        if not values["name"]:
            raise HTTPException(422, {"code": "name_empty"})
    if body.slug is not None:
        values["slug"] = body.slug.strip().lower()
        if not _SLUG.match(values["slug"]) or "--" in values["slug"]:
            raise HTTPException(422, {"code": "slug_invalid"})
        if db.select_one("tenants", {"select": "id", "slug": f"eq.{values['slug']}", "id": f"neq.{tid}"}):
            raise HTTPException(409, {"code": "slug_taken"})
    if values:
        db.update("tenants", {"id": f"eq.{tid}"}, values)
    return db.select_one("tenants", {"select": "name,slug", "id": f"eq.{tid}"})
