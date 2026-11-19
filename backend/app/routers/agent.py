"""Try the agent from the panel: answers with the business's real instructions
and knowledge, but writes nothing (no thread, no escalation, no quota)."""
import threading
import time
from collections import defaultdict, deque
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from google.genai import types
from pydantic import BaseModel, Field

from .. import db
from ..agent import context
from ..agent_defaults import DEFAULTS, default_for
from ..agent import loop as agent_loop
from ..agent.gemini import AgentUnavailable
from ..agent.tools import Toolbox
from ..tenancy import current_tenant_id

router = APIRouter(prefix="/agent")

# Each test message costs a model call: at most 30 per business per 10 minutes.
_RATE_LIMIT, _RATE_WINDOW = 30, 600
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _rate_limit(tenant_id: str) -> None:
    now = time.time()
    with _hits_lock:
        q = _hits[tenant_id]
        while q and now - q[0] > _RATE_WINDOW:
            q.popleft()
        if len(q) >= _RATE_LIMIT:
            raise HTTPException(429, "Too many test messages. Try again in a few minutes.")
        q.append(now)


class TestMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class TestRequest(BaseModel):
    messages: list[TestMessage] = Field(min_length=1, max_length=30)
    channel: Literal["widget", "whatsapp", "instagram", "email"] = "widget"


@router.post("/test")
def test_agent(req: TestRequest, tenant_id: str = Depends(current_tenant_id)):
    if req.messages[-1].role != "user":
        raise HTTPException(400, "The last message must be from the customer")
    _rate_limit(tenant_id)

    history = [types.Content(role="user" if m.role == "user" else "model",
                             parts=[types.Part(text=m.content or " ")])
               for m in req.messages]
    while history and history[0].role != "user":
        history.pop(0)

    ctx = context.load(tenant_id)
    try:
        result = agent_loop.run(ctx, history, Toolbox(tenant_id, dry_run=True), channel=req.channel)
    except AgentUnavailable as e:
        print(f"[agent test] unavailable: {e}")
        raise HTTPException(503, "The agent is not available right now. Check GEMINI_API_KEY.")
    return {
        "reply": result.text,
        "escalated": result.escalated,
        "tools": result.tools_used,
        "articles": len(ctx.articles),
    }


# ── Agent settings ─────────────────────────────────────────────────────

_SETTINGS = "instructions,tone,default_language,greeting,collect_contact,updated_at"


class SettingsIn(BaseModel):
    instructions: str = Field(default="", max_length=5000)
    tone: Literal["friendly", "professional", "casual", "formal"] = "friendly"
    default_language: Literal["en", "he", "ar"] = "en"
    greeting: str = Field(default="", max_length=500)
    collect_contact: Literal["email", "phone", "either", "none"] = "email"


@router.get("/settings")
def get_settings_(tenant_id: str = Depends(current_tenant_id)):
    row = db.select_one("agent_settings", {"select": _SETTINGS, "tenant_id": f"eq.{tenant_id}"})
    if row is None:   # created at signup; recreate if it ever went missing
        row = db.insert("agent_settings", {"tenant_id": tenant_id})[0]
    return _out(row)


@router.put("/settings")
def put_settings(body: SettingsIn, tenant_id: str = Depends(current_tenant_id)):
    values = {
        "instructions": body.instructions.strip(),
        "tone": body.tone,
        "default_language": body.default_language,
        # Empty = use the default text for the language.
        "greeting": body.greeting.strip() or None,
        "collect_contact": body.collect_contact,
    }
    rows = db.update("agent_settings", {"tenant_id": f"eq.{tenant_id}"}, values)
    if not rows:
        rows = db.insert("agent_settings", {"tenant_id": tenant_id, **values})
    return _out(rows[0])


def _out(row: dict) -> dict:
    """Settings as the panel shows them: an empty greeting is filled with the
    default for the language. The defaults for every language come along, so
    the panel can swap the greeting when the language changes."""
    lang = row.get("default_language") or "en"
    return {
        "instructions": row.get("instructions") or "",
        "tone": row.get("tone") or "friendly",
        "default_language": lang,
        "greeting": row.get("greeting") or default_for(lang, "greeting"),
        "collect_contact": row.get("collect_contact") or "email",
        "updated_at": row.get("updated_at"),
        "defaults": DEFAULTS,
    }
