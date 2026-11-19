"""Every incoming customer message — from the widget, WhatsApp, Instagram or
email — goes through receive_message(): store it, then queue a reply."""
from datetime import datetime, timedelta, timezone
from typing import Any

from . import alerts, db, jobs
from .config import get_settings

# Customers often send one thought as several quick messages. Waiting a moment
# lets them land, and "newest message wins" makes sure only one reply goes out.
REPLY_DELAY_SECONDS = 2.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_or_create_contact(channel: dict, external_id: str, name: str | None = None,
                          email: str | None = None, phone: str | None = None) -> dict:
    row = {"tenant_id": channel["tenant_id"], "channel_id": channel["id"], "external_id": external_id}
    if name:
        row["name"] = name[:120]
    if email:
        row["email"] = email[:200]
    if phone:
        row["phone"] = phone[:40]
    # Merge only the fields we were given; an existing name is never blanked.
    stored = db.insert("contacts", row, on_conflict="channel_id,external_id", merge=True)
    return stored[0]


def get_or_create_thread(channel: dict, contact: dict, external_thread_id: str | None = None) -> dict:
    params = {"select": "*", "channel_id": f"eq.{channel['id']}", "contact_id": f"eq.{contact['id']}"}
    thread = db.select_one("threads", params)
    if thread:
        if external_thread_id and thread.get("external_thread_id") != external_thread_id:
            # Replies go to this conversation id (e.g. Zernio's), so keep it current.
            db.update("threads", {"id": f"eq.{thread['id']}"}, {"external_thread_id": external_thread_id})
            thread["external_thread_id"] = external_thread_id
        return thread
    row = {"tenant_id": channel["tenant_id"], "channel_id": channel["id"], "contact_id": contact["id"]}
    if external_thread_id:
        row["external_thread_id"] = external_thread_id
    created = db.insert("threads", row, on_conflict="channel_id,contact_id", merge=False)
    return created[0] if created else db.select_one("threads", params)   # lost a race: re-read


def receive_message(
    channel: dict,
    external_contact_id: str,
    text: str = "",
    *,
    contact_name: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    attachment_url: str | None = None,
    attachment_mime: str | None = None,
    external_message_id: str | None = None,
    external_thread_id: str | None = None,
    auto_reply: bool = True,
) -> dict[str, Any]:
    """Store a customer's message and, if the agent should answer, queue it.
    `channel` is a row of the channels table. Returns ids for the caller."""
    contact = get_or_create_contact(channel, external_contact_id, contact_name, contact_email, contact_phone)
    thread = get_or_create_thread(channel, contact, external_thread_id)

    msg = db.insert("messages", {
        "tenant_id": channel["tenant_id"], "thread_id": thread["id"], "role": "user",
        "content": (text or "")[:8000], "attachment_url": attachment_url,
        "attachment_mime": attachment_mime, "external_id": external_message_id,
    })[0]
    preview = (text or "").strip()[:140] or ("📷" if (attachment_mime or "").startswith("image/") else "[attachment]")
    db.update("threads", {"id": f"eq.{thread['id']}"},
              {"unread": True, "last_message_at": _now(), "last_message_preview": preview})

    if thread.get("status") == "escalated":
        if _team_went_quiet(thread):
            # Nobody from the team has written for a while: the agent takes the
            # conversation back and answers this message.
            db.update("threads", {"id": f"eq.{thread['id']}"}, {"status": "bot", "escalation_reason": None})
            db.insert("messages", {"tenant_id": channel["tenant_id"], "thread_id": thread["id"], "role": "system",
                                   "content": "Handed back to the agent: no team reply for "
                                              f"{get_settings().handback_hours:g} hour(s)."})
            thread["status"] = "bot"
        else:
            alerts.queue_alert(channel["tenant_id"], thread["id"], "customer_message")
    elif channel.get("mode") != "auto":
        # Human-only channel: every new message needs the team.
        alerts.queue_alert(channel["tenant_id"], thread["id"], "customer_message")

    job_id = None
    if auto_reply and channel.get("mode") == "auto" and thread.get("status") == "bot":
        epoch = db.rpc("bump_reply_epoch", {"p_thread": thread["id"]})
        job_id = jobs.enqueue("reply", channel["tenant_id"],
                              {"thread_id": thread["id"], "epoch": epoch},
                              delay_seconds=REPLY_DELAY_SECONDS)

    return {"thread_id": thread["id"], "message_id": msg["id"], "contact_id": contact["id"], "job_id": job_id}


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def _team_went_quiet(thread: dict) -> bool:
    """True when the team took the conversation (or last wrote in it) more than
    handback_hours ago."""
    marks = [t for t in (_parse(thread.get("escalated_at")), _parse(thread.get("human_last_at"))) if t]
    if not marks:
        return True
    return max(marks) < datetime.now(timezone.utc) - timedelta(hours=get_settings().handback_hours)
