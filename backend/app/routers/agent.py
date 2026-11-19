"""Try the agent from the panel: answers with the business's real instructions
and knowledge, but writes nothing (no thread, no escalation, no quota)."""
import threading
import time
from collections import defaultdict, deque
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from google.genai import types
from pydantic import BaseModel, Field

from ..agent import context
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
