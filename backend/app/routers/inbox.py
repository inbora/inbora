"""The team's inbox: every conversation from every channel, in one place."""
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from google.genai import types
from pydantic import BaseModel, Field

from .. import channels, db, jobs, media
from ..agent import context, history
from ..agent import loop as agent_loop
from ..agent.gemini import AgentUnavailable
from ..agent.tools import Toolbox
from ..auth import CurrentUser, current_user
from ..inbound import REPLY_DELAY_SECONDS
from ..tenancy import current_tenant_id

router = APIRouter(prefix="/inbox")

MAX_THREAD_MESSAGES = 300


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _thread(tenant_id: str, thread_id: str) -> dict:
    t = db.select_one("threads", {"select": "*", "id": f"eq.{thread_id}", "tenant_id": f"eq.{tenant_id}"})
    if t is None:
        raise HTTPException(404, "Conversation not found")
    return t


def _note(t: dict, text: str) -> None:
    db.insert("messages", {"tenant_id": t["tenant_id"], "thread_id": t["id"], "role": "system", "content": text})


@router.get("/counts")
def counts(tenant_id: str = Depends(current_tenant_id)):
    rows = db.rpc("inbox_counts", {"p_tenant": tenant_id}) or [{}]
    r = rows[0] if isinstance(rows, list) else rows
    return {"escalated": int(r.get("escalated") or 0), "unread": int(r.get("unread") or 0)}


@router.get("/threads")
def list_threads(
    tenant_id: str = Depends(current_tenant_id),
    filter: Literal["all", "escalated", "unread", "bot"] = "all",
    channel: Literal["widget", "whatsapp", "instagram", "email"] | None = None,
    q: str | None = Query(default=None, max_length=100),
    days: int | None = Query(default=None, ge=1, le=3650),
    date_from: date | None = None,
    date_to: date | None = None,
    before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    start = None
    if days:
        start = datetime.now(timezone.utc) - timedelta(days=days)
    elif date_from:
        start = datetime.combine(date_from, datetime.min.time(), timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), timezone.utc) if date_to else None
    rows = db.rpc("inbox_threads", {
        "p_tenant": tenant_id, "p_filter": filter, "p_channel": channel, "p_q": (q or "").strip() or None,
        "p_from": start.isoformat() if start else None, "p_to": end.isoformat() if end else None,
        "p_before": before.isoformat() if before else None, "p_limit": limit,
    }) or []
    return {"threads": rows, "has_more": len(rows) == limit}


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str, after: int | None = None, mark_read: bool = True,
               tenant_id: str = Depends(current_tenant_id)):
    """The conversation with its messages. With `after`, only newer messages
    (used for polling an open conversation)."""
    t = _thread(tenant_id, thread_id)
    params = {"select": "id,role,content,attachment_url,attachment_mime,author_id,delivery_error,created_at",
              "thread_id": f"eq.{thread_id}"}
    if after is not None:
        params.update({"id": f"gt.{after}", "order": "id.asc"})
        msgs = db.select("messages", params)
    else:
        params.update({"order": "id.desc", "limit": str(MAX_THREAD_MESSAGES)})
        msgs = list(reversed(db.select("messages", params)))
    if mark_read and t["unread"]:
        db.update("threads", {"id": f"eq.{thread_id}"}, {"unread": False})
        t["unread"] = False

    authors = sorted({m["author_id"] for m in msgs if m.get("author_id")})
    names = {}
    if authors:
        for p in db.select("profiles", {"select": "id,full_name,email", "id": f"in.({','.join(authors)})"}):
            names[p["id"]] = p.get("full_name") or (p.get("email") or "").split("@")[0]
    for m in msgs:
        m["author_name"] = names.get(m.pop("author_id", None) or "")

    contact = db.select_one("contacts", {"select": "id,name,email,phone,username,external_id", "id": f"eq.{t['contact_id']}"})
    channel = db.select_one("channels", {"select": "id,type,mode", "id": f"eq.{t['channel_id']}"})
    return {"thread": t, "contact": contact, "channel": channel, "messages": msgs}


class ReadState(BaseModel):
    unread: bool


@router.post("/threads/{thread_id}/read")
def set_read(thread_id: str, body: ReadState, tenant_id: str = Depends(current_tenant_id)):
    _thread(tenant_id, thread_id)
    db.update("threads", {"id": f"eq.{thread_id}"}, {"unread": body.unread})
    return {"ok": True}


class ReplyImage(BaseModel):
    base64: str = Field(max_length=7_500_000)     # about 5 MB once decoded
    mime: str = Field(max_length=40)


class Reply(BaseModel):
    text: str = Field(default="", max_length=4000)
    image: ReplyImage | None = None


@router.post("/threads/{thread_id}/reply")
def reply(thread_id: str, body: Reply, user: CurrentUser = Depends(current_user),
          tenant_id: str = Depends(current_tenant_id)):
    """A team member answers. The team now owns the conversation: the agent
    stays quiet until someone hands it back (or the team goes quiet for an hour)."""
    t = _thread(tenant_id, thread_id)
    text = body.text.strip()
    if not text and not body.image:
        raise HTTPException(422, "The reply is empty")
    image_url = image_mime = None
    if body.image:
        try:
            image_url = media.upload_base64(body.image.base64, body.image.mime, tenant_id, thread_id)
        except media.MediaError as e:
            raise HTTPException(422, str(e))
        image_mime = body.image.mime
    msg = db.insert("messages", {"tenant_id": tenant_id, "thread_id": thread_id, "role": "human",
                                 "content": text, "author_id": user.id,
                                 "attachment_url": image_url, "attachment_mime": image_mime})[0]
    now = _now()
    values = {"status": "escalated", "human_last_at": now, "unread": False,
              "last_message_at": now, "last_message_preview": (text or "📷")[:140]}
    if t["status"] != "escalated":
        values["escalated_at"] = now
        values["escalation_reason"] = "Answered by the team"
    db.update("threads", {"id": f"eq.{thread_id}"}, values)
    db.rpc("bump_reply_epoch", {"p_thread": thread_id})     # cancels a reply the agent was about to send

    channel = db.select_one("channels", {"select": "*", "id": f"eq.{t['channel_id']}"}) or {}
    contact = db.select_one("contacts", {"select": "*", "id": f"eq.{t['contact_id']}"}) or {}
    try:
        error = channels.deliver(channel, t, contact, text, image_url=image_url, key=f"msg-{msg['id']}")
    except Exception as e:  # noqa: BLE001 — the reply is saved; say it didn't go out
        print(f"[inbox] delivery failed for {thread_id}: {e}")
        error = "error: Sending failed. Please try again."
    if error:
        db.update("messages", {"id": f"eq.{msg['id']}"}, {"delivery_error": error})
        msg["delivery_error"] = error
    return {"message": {**msg, "author_name": None}, "delivered": error is None, "error": error}


@router.post("/threads/{thread_id}/takeover")
def takeover(thread_id: str, tenant_id: str = Depends(current_tenant_id)):
    t = _thread(tenant_id, thread_id)
    if t["status"] == "escalated":
        return {"status": "escalated"}
    now = _now()
    db.update("threads", {"id": f"eq.{thread_id}"},
              {"status": "escalated", "escalated_at": now, "escalation_reason": "Taken over by the team"})
    db.rpc("bump_reply_epoch", {"p_thread": thread_id})
    _note(t, "The team took over the conversation.")
    return {"status": "escalated"}


@router.post("/threads/{thread_id}/handback")
def handback(thread_id: str, tenant_id: str = Depends(current_tenant_id)):
    """Give the conversation back to the agent. If the customer's last message
    is still unanswered, the agent answers it now."""
    t = _thread(tenant_id, thread_id)
    if t["status"] == "bot":
        return {"status": "bot", "answering": False}
    db.update("threads", {"id": f"eq.{thread_id}"}, {"status": "bot", "escalation_reason": None})
    _note(t, "Handed back to the agent.")

    last = db.select_one("messages", {"select": "role", "thread_id": f"eq.{thread_id}",
                                      "role": "neq.system", "order": "id.desc", "limit": "1"})
    channel = db.select_one("channels", {"select": "mode", "id": f"eq.{t['channel_id']}"}) or {}
    answering = bool(last and last["role"] == "user" and channel.get("mode") == "auto")
    if answering:
        epoch = db.rpc("bump_reply_epoch", {"p_thread": thread_id})
        jobs.enqueue("reply", tenant_id, {"thread_id": thread_id, "epoch": epoch},
                     delay_seconds=REPLY_DELAY_SECONDS)
    return {"status": "bot", "answering": answering}


# ── AI draft: the agent suggests a reply the team member can edit and send

_DRAFT_LIMIT, _DRAFT_WINDOW = 60, 600
_draft_hits: dict[str, deque] = defaultdict(deque)
_draft_lock = threading.Lock()


def _draft_rate(tenant_id: str) -> None:
    now = time.time()
    with _draft_lock:
        q = _draft_hits[tenant_id]
        while q and now - q[0] > _DRAFT_WINDOW:
            q.popleft()
        if len(q) >= _DRAFT_LIMIT:
            raise HTTPException(429, "Too many drafts. Try again in a few minutes.")
        q.append(now)


class DraftRequest(BaseModel):
    direction: str | None = Field(default=None, max_length=1000)
    # Whatever is in the reply box: the model builds on it if it's relevant.
    current_text: str | None = Field(default=None, max_length=4000)


@router.post("/threads/{thread_id}/draft")
def draft(thread_id: str, body: DraftRequest, user: CurrentUser = Depends(current_user),
          tenant_id: str = Depends(current_tenant_id)):
    t = _thread(tenant_id, thread_id)
    _draft_rate(tenant_id)
    rows = db.select("messages", {
        "select": "role,content,attachment_url,attachment_mime",
        "thread_id": f"eq.{thread_id}", "order": "id.desc", "limit": str(history.MAX_MESSAGES),
    })
    rows.reverse()
    convo = history.build(rows)
    if not convo:
        raise HTTPException(422, "There is no customer message to answer yet")
    if convo[-1].role != "user":
        # The team or the agent wrote last: ask for the next message anyway.
        convo.append(types.Content(role="user", parts=[types.Part(
            text="[Note from the system, not the customer: write the team's next message in this conversation.]")]))

    channel = db.select_one("channels", {"select": "type", "id": f"eq.{t['channel_id']}"}) or {}
    contact = db.select_one("contacts", {"select": "name", "id": f"eq.{t['contact_id']}"}) or {}
    ctx = context.load(tenant_id)
    me = db.select_one("profiles", {"select": "full_name", "id": f"eq.{user.id}"}) or {}
    toolbox = Toolbox(tenant_id, thread_id=thread_id, dry_run=True)
    try:
        result = agent_loop.run(ctx, convo, toolbox, channel=channel.get("type", "widget"),
                                customer_name=contact.get("name"), as_rep=True,
                                rep_direction=(body.direction or "").strip() or None,
                                rep_name=me.get("full_name"),
                                rep_text=(body.current_text or "").strip() or None)
    except AgentUnavailable:
        raise HTTPException(503, "The assistant isn't available right now. Try again in a moment.")
    if result.fallback:
        raise HTTPException(503, "The assistant couldn't write a draft. Try again in a moment.")
    return {"text": result.text}
