"""The logged-in user, their business (tenant) and its plan."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db
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

    sub = db.select_one("subscriptions", {
        "select": "limits,period_start,period_end,status",
        "tenant_id": f"eq.{tenant['id']}",
        "status": "eq.active",
    })
    usage = db.select_one("usage_counters", {
        "select": "conversations_used,bonus_conversations,period_start",
        "tenant_id": f"eq.{tenant['id']}",
        "order": "period_start.desc",
    })

    plan = None
    if sub:
        limits = sub["limits"]
        quota = int(limits.get("conversation_quota", 0))
        bonus = int((usage or {}).get("bonus_conversations", 0))
        plan = {
            "code": limits.get("plan_code"),
            "name": limits.get("plan_name"),
            "billing_period": limits.get("billing_period"),
            "conversation_quota": quota + bonus,
            "conversations_used": int((usage or {}).get("conversations_used", 0)),
            "max_channels": limits.get("max_channels"),
            "kb_char_limit": limits.get("kb_char_limit"),
            "show_branding": bool(limits.get("show_branding", True)),
            "period_end": sub["period_end"],
        }

    profile = db.select_one("profiles", {"select": "full_name", "id": f"eq.{user.id}"}) or {}
    return {
        "user": {"id": user.id, "email": user.email, "is_super_admin": user.is_super_admin,
                 "full_name": profile.get("full_name") or ""},
        "tenant": {**tenant, "role": membership["role"]},
        "plan": plan,
    }


class ProfileIn(BaseModel):
    full_name: str = Field(default="", max_length=80)


@router.put("/me/profile")
def update_profile(body: ProfileIn, user: CurrentUser = Depends(current_user)):
    """The user's own name: shown on their replies in the inbox and used to sign AI drafts."""
    name = " ".join(body.full_name.split())
    db.update("profiles", {"id": f"eq.{user.id}"}, {"full_name": name or None})
    return {"full_name": name}
