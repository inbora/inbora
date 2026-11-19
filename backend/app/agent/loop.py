"""The tool-use loop (ported from Grinta's run_loop)."""
import time
from dataclasses import dataclass, field

from google.genai import types

from ..config import get_settings
from . import gemini, guards
from .context import TenantContext
from .prompt import build_system_prompt
from .tools import BOT_TOOLS, Toolbox

MAX_ROUNDS = 5


@dataclass
class AgentResult:
    text: str
    escalated: bool = False
    tools_used: list[str] = field(default_factory=list)
    fallback: bool = False   # True when the customer got the canned "technical problem" text


def run(
    ctx: TenantContext,
    history: list[types.Content],
    toolbox: Toolbox,
    channel: str = "widget",
    customer_name: str | None = None,
    as_rep: bool = False,
    rep_direction: str | None = None,
    rep_name: str | None = None,
    rep_text: str | None = None,
) -> AgentResult:
    """Answer the last customer message. Raises gemini.AgentUnavailable if no
    model could answer at all (the caller decides whether to retry)."""
    system = build_system_prompt(ctx, channel=channel,
                                 customer_name=guards.plausible_name(customer_name),
                                 as_rep=as_rep, rep_direction=rep_direction, rep_name=rep_name,
                                 rep_text=rep_text)
    tools = None if as_rep else BOT_TOOLS     # a team member's draft never escalates
    history = list(history)
    deadline = time.monotonic() + get_settings().agent_deadline_seconds

    for round_no in range(MAX_ROUNDS):
        if round_no and time.monotonic() > deadline:
            print("[agent] reply deadline passed between tool rounds")
            break
        resp = gemini.generate(history, system, tools, deadline=deadline)
        content = resp.candidates[0].content
        history.append(content)
        parts = content.parts or []
        calls = [p for p in parts if p.function_call is not None]

        if not calls:
            # Only the answer reaches the customer — never "thought" parts or a
            # reasoning block the model wrote out as text.
            text = "".join(p.text for p in parts if p.text and not getattr(p, "thought", False))
            text = guards.strip_reasoning(text.strip())
            if not text or guards.looks_like_raw_output(text):
                if text:
                    print(f"[agent] raw output blocked: {text[:200]}")
                return AgentResult(guards.fallback(ctx.default_language), toolbox.escalated,
                                   toolbox.calls, fallback=True)
            return AgentResult(text, toolbox.escalated, toolbox.calls)

        responses = []
        for p in calls:
            fc = p.function_call
            result = toolbox.execute(fc.name, dict(fc.args or {}))
            responses.append(types.Part(function_response=types.FunctionResponse(
                name=fc.name, response={"result": result})))
        history.append(types.Content(role="user", parts=responses))

    return AgentResult(guards.fallback(ctx.default_language), toolbox.escalated,
                       toolbox.calls, fallback=True)
