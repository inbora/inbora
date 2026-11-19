"""Events from Zernio: WhatsApp, Instagram and email messages, and account changes.

One webhook endpoint for every business. Each event names the Zernio profile
it belongs to (profiles[].externalId = our tenant id) and the account
(account.accountId = channels.external_account_id)."""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from .. import alerts, db, email_in, inbound, jobs, zernio
from .channels import upsert_messaging_channel

router = APIRouter()

# An outgoing message this soon after the customer's is an automatic reply
# (WhatsApp Business greeting / away message), not a person taking over.
AUTO_REPLY_SECONDS = 4
ECHO_WINDOW_SECONDS = 180


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


@router.post("/zernio/webhook")
async def webhook(request: Request):
    raw = await request.body()
    if not zernio.verify_signature(raw, request.headers.get("X-Zernio-Signature", "")):
        raise HTTPException(401, "bad signature")
    try:
        payload = json.loads(raw)
    except ValueError:
        return {"ok": True}
    return await run_in_threadpool(handle_event, payload)


def handle_event(payload: dict) -> dict:
    event, event_id = payload.get("event") or "", payload.get("id") or ""
    if payload.get("test") or event not in HANDLERS:
        return {"ok": True, "ignored": event}
    if event_id and not db.rpc("mark_event_processed", {"p_provider": "zernio", "p_event_id": event_id}):
        return {"ok": True, "duplicate": True}
    try:
        outcome = HANDLERS[event](payload)
    except Exception:
        # Let Zernio retry: forget that we saw this event.
        if event_id:
            db.delete("processed_events", {"provider": "eq.zernio", "event_id": f"eq.{event_id}"})
        raise
    print(f"[zernio] {event} {event_id}: {outcome}")
    return {"ok": True, "outcome": outcome}


# ── Routing helpers

def _tenant_ids(payload: dict) -> set[str]:
    return {p.get("externalId") for p in (payload.get("profiles") or []) if p.get("externalId")}


def _account_id(payload: dict) -> str:
    acc = payload.get("account") or {}
    return acc.get("accountId") or acc.get("id") or ""


def _channel(payload: dict) -> dict | None:
    account_id = _account_id(payload)
    if not account_id:
        return None
    ch = db.select_one("channels", {"select": "*", "external_account_id": f"eq.{account_id}",
                                    "status": "neq.disconnected", "order": "created_at.desc", "limit": "1"})
    if ch is None or ch["type"] not in zernio.CHANNEL_TYPES:
        return None
    tenants = _tenant_ids(payload)
    if tenants and ch["tenant_id"] not in tenants:     # never cross businesses
        print(f"[zernio] account {account_id} profile/tenant mismatch, ignored")
        return None
    return ch


def _participant(payload: dict) -> tuple[str, str | None, str | None, str | None]:
    """(external id, name, phone, @username) of the customer, in either direction."""
    conv = payload.get("conversation") or {}
    msg = payload.get("message") or {}
    sender = msg.get("sender") or {}
    pid = conv.get("participantId") or ""
    if not pid and msg.get("direction") == "incoming":
        pid = sender.get("id") or ""
    name = (conv.get("participantName") or "").strip() or None
    username = (conv.get("participantUsername") or "").strip().lstrip("@") or None
    if name and username and name.lstrip("@") == username:
        name = None                      # no real name: just the @username
    phone = sender.get("phoneNumber") if msg.get("direction") == "incoming" else None
    return pid, name, phone, username


def _first_image(msg: dict) -> tuple[str | None, str | None, str | None]:
    """(url, mime, label for other attachment types)."""
    other = None
    for att in msg.get("attachments") or []:
        kind = (att.get("type") or "").lower()
        if kind in ("image", "photo", "sticker") and att.get("url"):
            return att["url"], "image/jpeg", None
        other = other or kind or "file"
    return None, None, other


# ── message.received: a customer wrote

def on_message_received(payload: dict) -> str:
    ch = _channel(payload)
    if ch is None:
        return "no-channel"
    if ch["type"] == "email":
        mid = email_in.message_id_from_webhook(payload)
        return email_in.ingest(ch, mid, email_in.hint_from_webhook(payload)) if mid else "no-message-id"
    msg = payload.get("message") or {}
    if (msg.get("platform") or ch["type"]) != ch["type"]:
        return "platform-mismatch"
    pid, name, phone, username = _participant(payload)
    if not pid:
        return "no-participant"
    image_url, image_mime, other = _first_image(msg)
    text = (msg.get("text") or "").strip()
    if not text and not image_url and other:
        text = f"[The customer sent a {other}]"
    standby = bool((payload.get("metadata") or {}).get("standby"))
    res = inbound.receive_message(
        ch, pid, text, contact_name=name, contact_phone=phone, contact_username=username,
        attachment_url=image_url, attachment_mime=image_mime,
        external_message_id=msg.get("id"),
        external_thread_id=(payload.get("conversation") or {}).get("id") or msg.get("conversationId"),
        auto_reply=not standby)          # another app answers this conversation
    if image_url:
        jobs.enqueue("media", ch["tenant_id"], {"message_id": res["message_id"], "url": image_url,
                                                 "thread_id": res["thread_id"]})
    return "stored+reply" if res["job_id"] else "stored"


# ── message.sent: our own send (skip) or a reply from the phone / Zernio inbox

def _is_echo(thread_id: str, text: str) -> bool:
    if not text:
        return False
    since = (_now() - timedelta(seconds=ECHO_WINDOW_SECONDS)).isoformat()
    rows = db.select("messages", {"select": "content", "thread_id": f"eq.{thread_id}",
                                  "role": "in.(assistant,human)", "created_at": f"gte.{since}",
                                  "order": "id.desc", "limit": "10"})
    return any((r.get("content") or "").strip() == text for r in rows)


def on_message_sent(payload: dict) -> str:
    msg = payload.get("message") or {}
    if msg.get("sentVia") == "api":
        return "own-send"                # Inbora sent it and already stored it
    ch = _channel(payload)
    if ch is None:
        return "no-channel"
    if ch["type"] == "email":
        # Someone answered from the mailbox itself (Gmail, Outlook...).
        mid = email_in.message_id_from_webhook(payload)
        return email_in.sent_from_mailbox(ch, mid, email_in.hint_from_webhook(payload)) if mid else "no-message-id"
    pid, name, _, username = _participant(payload)
    if not pid:
        return "no-participant"
    text = (msg.get("text") or "").strip()
    image_url, image_mime, _ = _first_image(msg)
    conv_id = (payload.get("conversation") or {}).get("id") or msg.get("conversationId")
    contact = inbound.get_or_create_contact(ch, pid, name, username=username)
    thread = inbound.get_or_create_thread(ch, contact, conv_id)
    if _is_echo(thread["id"], text):
        return "echo"

    row = db.insert("messages", {"tenant_id": ch["tenant_id"], "thread_id": thread["id"], "role": "human",
                                 "content": text[:8000], "attachment_url": image_url,
                                 "attachment_mime": image_mime, "external_id": msg.get("id")})[0]
    now = _now().isoformat()
    values = {"last_message_at": now, "last_message_preview": (text or "📷")[:140], "archived_at": None}

    last_customer = db.select_one("messages", {"select": "created_at", "thread_id": f"eq.{thread['id']}",
                                               "role": "eq.user", "order": "id.desc", "limit": "1"})
    sent_at = _ts(msg.get("sentAt")) or _now()
    asked_at = _ts((last_customer or {}).get("created_at"))
    automatic = asked_at is not None and (sent_at - asked_at).total_seconds() < AUTO_REPLY_SECONDS
    if not automatic:
        # A person answered from the phone (or Zernio's inbox): the team owns it now.
        values["human_last_at"] = now
        if thread["status"] != "escalated":
            values.update({"status": "escalated", "escalated_at": now,
                           "escalation_reason": "Answered from the phone"})
    db.update("threads", {"id": f"eq.{thread['id']}"}, values)
    if not automatic:
        db.rpc("bump_reply_epoch", {"p_thread": thread["id"]})   # drop a reply the agent was writing
    if image_url:
        jobs.enqueue("media", ch["tenant_id"], {"message_id": row["id"], "url": image_url, "thread_id": thread["id"]})
    return "automatic-reply" if automatic else "phone-reply"


# ── Accounts

def on_account_connected(payload: dict) -> str:
    acc = payload.get("account") or {}
    kind = zernio.channel_type(acc.get("platform"))
    tenants = _tenant_ids(payload)
    if kind is None or len(tenants) != 1:
        return "ignored"
    tenant_id = next(iter(tenants))
    if not db.select_one("tenants", {"select": "id", "id": f"eq.{tenant_id}"}):
        return "unknown-tenant"
    upsert_messaging_channel(tenant_id, kind, acc)
    return "channel-saved"


def on_account_disconnected(payload: dict) -> str:
    ch = _channel(payload)
    if ch is None:
        return "no-channel"
    acc = payload.get("account") or {}
    if acc.get("disconnectionType") == "intentional":
        db.update("channels", {"id": f"eq.{ch['id']}"}, {"status": "disconnected", "updated_at": _now().isoformat()})
        return "removed"
    db.update("channels", {"id": f"eq.{ch['id']}"}, {"status": "error", "updated_at": _now().isoformat()})
    alerts.queue_channel_alert(ch["tenant_id"], ch["id"])
    return "marked-error"


HANDLERS = {
    "message.received": on_message_received,
    "message.sent": on_message_sent,
    "account.connected": on_account_connected,
    "account.disconnected": on_account_disconnected,
}
