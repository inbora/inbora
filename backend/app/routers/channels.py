"""The business's channels: website chat (Step 4), WhatsApp and Instagram
(Step 5) and email (Step 6), the last three through Zernio."""
import re
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, plans, zernio
from ..config import get_settings
from ..tenancy import current_tenant_id

router = APIRouter(prefix="/channels")

DEFAULT_COLOR = "#0e9f6e"
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _out(c: dict) -> dict:
    cfg = c.get("config") or {}
    return {
        "id": c["id"], "type": c["type"], "mode": c["mode"], "status": c["status"],
        "display_name": c.get("display_name"), "widget_key": c.get("widget_key"),
        "color": cfg.get("color", DEFAULT_COLOR), "position": cfg.get("position", "right"),
        "created_at": c.get("created_at"), "updated_at": c.get("updated_at"),
    }


def _active(rows: list[dict]) -> list[dict]:
    return [c for c in rows if c["status"] != "disconnected"]


@router.get("")
def list_channels(tenant_id: str = Depends(current_tenant_id)):
    rows = db.select("channels", {"select": "*", "tenant_id": f"eq.{tenant_id}", "order": "created_at.asc"})
    max_channels = int(plans.limits(tenant_id).get("max_channels") or 1)
    return {"channels": [_out(c) for c in rows], "max_channels": max_channels, "used": len(_active(rows)),
            "messaging_ready": zernio.configured()}


@router.post("/widget")
def create_widget(tenant_id: str = Depends(current_tenant_id)):
    """Turn on the website chat. A business has one; calling again returns it
    (and turns it back on if it was switched off)."""
    rows = db.select("channels", {"select": "*", "tenant_id": f"eq.{tenant_id}"})
    existing = next((c for c in rows if c["type"] == "widget"), None)
    max_channels = int(plans.limits(tenant_id).get("max_channels") or 1)
    others = [c for c in _active(rows) if c["type"] != "widget"]

    if existing and existing["status"] != "disconnected":
        return _out(existing)
    if len(others) >= max_channels:
        raise HTTPException(422, detail={"code": "channel_limit", "limit": max_channels})
    if existing:
        changed = db.update("channels", {"id": f"eq.{existing['id']}"},
                            {"status": "connected", "updated_at": datetime.now(timezone.utc).isoformat()})
        return _out(changed[0])
    created = db.insert("channels", {
        "tenant_id": tenant_id, "type": "widget", "mode": "auto", "status": "connected",
        "display_name": "Website chat", "widget_key": "wk_" + secrets.token_urlsafe(18),
        "config": {"color": DEFAULT_COLOR, "position": "right"},
    })
    return _out(created[0])


class ChannelUpdate(BaseModel):
    mode: Literal["auto", "human"] | None = None
    color: str | None = Field(default=None, max_length=7)
    position: Literal["right", "left"] | None = None
    enabled: bool | None = None


@router.put("/{channel_id}")
def update_channel(channel_id: str, body: ChannelUpdate, tenant_id: str = Depends(current_tenant_id)):
    ch = db.select_one("channels", {"select": "*", "id": f"eq.{channel_id}", "tenant_id": f"eq.{tenant_id}"})
    if ch is None:
        raise HTTPException(404, "Channel not found")
    values: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if body.mode is not None:
        values["mode"] = body.mode
    if body.color is not None or body.position is not None:
        cfg = dict(ch.get("config") or {})
        if body.color is not None:
            if not _COLOR.match(body.color):
                raise HTTPException(422, "Colour must look like #0e9f6e")
            cfg["color"] = body.color.lower()
        if body.position is not None:
            cfg["position"] = body.position
        values["config"] = cfg
    if body.enabled is not None and ch["type"] != "widget":
        raise HTTPException(422, "Use Connect / Disconnect for this channel")
    if body.enabled is not None:
        if body.enabled and ch["status"] == "disconnected":
            rows = db.select("channels", {"select": "id,status", "tenant_id": f"eq.{tenant_id}"})
            max_channels = int(plans.limits(tenant_id).get("max_channels") or 1)
            if len([c for c in _active(rows) if c["id"] != channel_id]) >= max_channels:
                raise HTTPException(422, detail={"code": "channel_limit", "limit": max_channels})
            values["status"] = "connected"
        elif not body.enabled:
            values["status"] = "disconnected"
    changed = db.update("channels", {"id": f"eq.{channel_id}", "tenant_id": f"eq.{tenant_id}"}, values)
    return _out(changed[0])


# ── WhatsApp, Instagram and email (Zernio)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _display_name(platform: str, account: dict) -> str:
    if platform == "email":
        return _account_email(account)[:120]
    name = account.get("username") or account.get("displayName") or ""
    if platform == "instagram" and name and not name.startswith("@"):
        name = "@" + name
    return name[:120]


def _account_email(account: dict) -> str:
    for k in ("email", "username", "displayName"):
        v = (account.get(k) or "").strip().lower()
        if "@" in v:
            return v
    return (account.get("username") or account.get("displayName") or "").strip()


def upsert_messaging_channel(tenant_id: str, platform: str, account: dict) -> dict:
    """Save (or refresh) the business's WhatsApp / Instagram / email channel
    after a successful connect. Used by the connect callback and the
    account.connected webhook, whichever arrives first."""
    account_id = account.get("accountId") or account.get("_id") or account.get("id")
    existing = db.select_one("channels", {"select": "*", "tenant_id": f"eq.{tenant_id}", "type": f"eq.{platform}",
                                          "order": "created_at.desc", "limit": "1"})
    values = {"external_account_id": account_id, "display_name": _display_name(platform, account),
              "status": "connected", "updated_at": _now()}
    if platform == "email":
        cfg = dict((existing or {}).get("config") or {})
        cfg["email"] = _account_email(account)
        if (existing or {}).get("external_account_id") != account_id or (existing or {}).get("status") != "connected":
            cfg["email_since"] = _now()      # read new mail only, from now on
        values["config"] = cfg
    if existing:
        return db.update("channels", {"id": f"eq.{existing['id']}"}, values)[0]
    # Email starts with the team answering (the agent can draft); chats start with the agent.
    mode = "human" if platform == "email" else "auto"
    return db.insert("channels", {"tenant_id": tenant_id, "type": platform, "mode": mode, **values})[0]


class ConnectRequest(BaseModel):
    # WhatsApp only: keep using the number in the WhatsApp Business app.
    whatsapp_app: bool = True


Platform = Literal["whatsapp", "instagram", "email"]


@router.post("/{platform}/connect")
def connect(platform: Platform, body: ConnectRequest, tenant_id: str = Depends(current_tenant_id)):
    """Start the one-click connect: returns the link to open (Meta's own
    WhatsApp signup, Instagram login, or the mailbox sign-in, run through Zernio)."""
    if not zernio.configured():
        raise HTTPException(503, detail={"code": "not_configured"})
    rows = db.select("channels", {"select": "*", "tenant_id": f"eq.{tenant_id}"})
    mine = next((c for c in rows if c["type"] == platform and c["status"] != "disconnected"), None)
    if mine and mine["status"] == "connected":
        raise HTTPException(409, detail={"code": "already_connected"})
    if not mine:   # reconnecting a broken channel doesn't need a free slot
        max_channels = int(plans.limits(tenant_id).get("max_channels") or 1)
        if len(_active(rows)) >= max_channels:
            raise HTTPException(422, detail={"code": "channel_limit", "limit": max_channels})
    try:
        profile_id = zernio.ensure_profile(tenant_id)
        url = zernio.connect_url(
            platform, profile_id, f"{get_settings().app_url.rstrip('/')}/channels?connect={platform}",
            whatsapp_app=body.whatsapp_app,
            reconnect_account_id=(mine or {}).get("external_account_id") if platform != "whatsapp" else None)
    except zernio.ZernioError as e:
        print(f"[channels] connect {platform} failed: {e.status} {e.message}")
        raise HTTPException(502, detail={"code": "zernio_error", "message": e.message})
    return {"url": url}


class CompleteRequest(BaseModel):
    account_id: str = Field(max_length=100)
    # The mailbox sign-in doesn't send it back; the business's own profile is used.
    profile_id: str | None = Field(default=None, max_length=100)


@router.post("/{platform}/complete")
def complete(platform: Platform, body: CompleteRequest, tenant_id: str = Depends(current_tenant_id)):
    """The browser came back from the connect flow. Check with Zernio that the
    account really belongs to this business before saving it."""
    tenant = db.select_one("tenants", {"select": "zernio_profile_id", "id": f"eq.{tenant_id}"}) or {}
    profile_id = tenant.get("zernio_profile_id")
    if not profile_id or (body.profile_id and body.profile_id != profile_id):
        raise HTTPException(403, "This account belongs to another business")
    try:
        account = zernio.find_account(profile_id, body.account_id)
    except zernio.ZernioError as e:
        raise HTTPException(502, detail={"code": "zernio_error", "message": e.message})
    if not account or (zernio.channel_type(account.get("platform")) or platform) != platform:
        raise HTTPException(404, "Account not found")
    return _out(upsert_messaging_channel(tenant_id, platform, account))


@router.post("/{channel_id}/disconnect")
def disconnect(channel_id: str, tenant_id: str = Depends(current_tenant_id)):
    """Disconnect WhatsApp / Instagram / email: removes it from Zernio too (so
    it stops costing anything) and keeps the conversations."""
    ch = db.select_one("channels", {"select": "*", "id": f"eq.{channel_id}", "tenant_id": f"eq.{tenant_id}"})
    if ch is None:
        raise HTTPException(404, "Channel not found")
    if ch["type"] in zernio.CHANNEL_TYPES and ch.get("external_account_id"):
        try:
            zernio.delete_account(ch["external_account_id"])
        except zernio.ZernioError as e:
            raise HTTPException(502, detail={"code": "zernio_error", "message": e.message})
    changed = db.update("channels", {"id": f"eq.{channel_id}"}, {"status": "disconnected", "updated_at": _now()})
    return _out(changed[0])
