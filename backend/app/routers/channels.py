"""The business's channels. Step 4 adds the website chat; WhatsApp and
Instagram (Zernio) come in Step 5, email (Unipile) in Step 6."""
import re
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, plans
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
        "created_at": c.get("created_at"),
    }


def _active(rows: list[dict]) -> list[dict]:
    return [c for c in rows if c["status"] != "disconnected"]


@router.get("")
def list_channels(tenant_id: str = Depends(current_tenant_id)):
    rows = db.select("channels", {"select": "*", "tenant_id": f"eq.{tenant_id}", "order": "created_at.asc"})
    max_channels = int(plans.limits(tenant_id).get("max_channels") or 1)
    return {"channels": [_out(c) for c in rows], "max_channels": max_channels, "used": len(_active(rows))}


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
