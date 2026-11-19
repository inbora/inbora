"""The agent's tools. Step 2 has two: escalate to a human, and save the
customer's email. Store integrations (orders, products) come later."""
import re
from datetime import datetime, timezone

from google.genai import types

from .. import db

DECLARATIONS = [
    types.FunctionDeclaration(
        name="escalate_to_human",
        description=(
            "Pass the conversation to the business's team. Use when you genuinely cannot "
            "help: the answer is not in your knowledge, the customer asks for a person, or "
            "the request needs someone at the business to act."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "reason": types.Schema(type=types.Type.STRING,
                                       description="Short reason, e.g. 'refund request'"),
                "summary": types.Schema(type=types.Type.STRING,
                                        description="What the customer needs, in one or two sentences"),
            },
            required=["reason", "summary"],
        ),
    ),
    types.FunctionDeclaration(
        name="collect_contact",
        description=(
            "Save the customer's own email address and/or phone number (and name, if known) "
            "so the team can get back to them. Never pass details that are not the customer's own."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "email": types.Schema(type=types.Type.STRING, description="The customer's email, if given"),
                "phone": types.Schema(type=types.Type.STRING, description="The customer's phone number, if given"),
                "name": types.Schema(type=types.Type.STRING, description="The customer's name, if known"),
            },
        ),
    ),
]

BOT_TOOLS = [types.Tool(function_declarations=DECLARATIONS)]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[\d\s().\-]{7,20}$")


class Toolbox:
    """Runs tool calls for one conversation. With dry_run (the test chat) nothing
    is written to the database."""

    def __init__(self, tenant_id: str, thread_id: str | None = None,
                 contact_id: str | None = None, dry_run: bool = False):
        self.tenant_id = tenant_id
        self.thread_id = thread_id
        self.contact_id = contact_id
        self.dry_run = dry_run
        self.escalated = False
        self.calls: list[str] = []

    def execute(self, name: str, args: dict) -> dict:
        self.calls.append(name)
        try:
            if name == "escalate_to_human":
                return self._escalate(str(args.get("reason", "")), str(args.get("summary", "")))
            if name in ("collect_contact", "collect_contact_email"):
                return self._collect(args.get("email"), args.get("phone"), args.get("name"))
            return {"error": f"unknown tool {name}"}
        except Exception as e:  # noqa: BLE001 — a tool failure must not crash the reply
            print(f"[tool] {name} failed: {e}")
            return {"error": "the action could not be completed right now"}

    def _escalate(self, reason: str, summary: str) -> dict:
        self.escalated = True
        if not self.dry_run and self.thread_id:
            db.update("threads", {"id": f"eq.{self.thread_id}", "tenant_id": f"eq.{self.tenant_id}"},
                      {"status": "escalated", "escalation_reason": reason[:300],
                       "escalated_at": datetime.now(timezone.utc).isoformat()})
            db.insert("messages", {
                "tenant_id": self.tenant_id, "thread_id": self.thread_id, "role": "system",
                "content": f"Escalated to the team: {reason}\n{summary}".strip()[:2000],
            })
            from ..alerts import queue_alert   # late import: alerts imports the agent package
            queue_alert(self.tenant_id, self.thread_id, "escalated", reason)
        return {"escalated": True,
                "next": "Tell the customer that their request was passed to the team and someone will get back to them."}

    def _collect(self, email, phone, name) -> dict:
        values: dict[str, str] = {}
        if isinstance(email, str) and email.strip():
            if not _EMAIL_RE.match(email.strip()):
                return {"saved": False, "reason": "invalid email address — ask the customer to check it"}
            values["email"] = email.strip().lower()
        if isinstance(phone, str) and phone.strip():
            if not _PHONE_RE.match(phone.strip()) or sum(c.isdigit() for c in phone) < 7:
                return {"saved": False, "reason": "invalid phone number — ask the customer to check it"}
            values["phone"] = phone.strip()
        if not values:
            return {"saved": False, "reason": "no email or phone number given"}
        if isinstance(name, str) and name.strip():
            values["name"] = name.strip()[:120]
        if not self.dry_run and self.contact_id:
            db.update("contacts", {"id": f"eq.{self.contact_id}", "tenant_id": f"eq.{self.tenant_id}"}, values)
        return {"saved": True}
