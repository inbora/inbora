"""Browser push subscriptions for the logged-in user."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db
from ..alerts import _send_push
from ..auth import CurrentUser, current_user
from ..config import get_settings

router = APIRouter(prefix="/push")


class Keys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class Subscription(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: Keys


@router.get("/public-key")
def public_key():
    key = get_settings().vapid_public_key
    if not key:
        raise HTTPException(404, "Push notifications are not set up")
    return {"key": key}


@router.post("/subscribe", status_code=204)
def subscribe(sub: Subscription, user: CurrentUser = Depends(current_user)):
    if not sub.endpoint.startswith("https://"):
        raise HTTPException(422, "Invalid endpoint")
    db.insert("push_subscriptions",
              {"user_id": user.id, "endpoint": sub.endpoint, "p256dh": sub.keys.p256dh, "auth": sub.keys.auth},
              on_conflict="endpoint", merge=True)


class Unsubscribe(BaseModel):
    endpoint: str = Field(max_length=1000)


@router.post("/unsubscribe", status_code=204)
def unsubscribe(body: Unsubscribe, user: CurrentUser = Depends(current_user)):
    db.delete("push_subscriptions", {"endpoint": f"eq.{body.endpoint}", "user_id": f"eq.{user.id}"})


@router.post("/test")
def test_push(user: CurrentUser = Depends(current_user)):
    sent = _send_push([user.id], "Inbora", "Notifications are working ✓", get_settings().app_url)
    return {"sent": sent}
