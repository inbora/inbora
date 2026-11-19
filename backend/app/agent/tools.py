"""The agent's tools. Step 2 has two: escalate to a human, and save the
customer's email. Store integrations (orders, products) come later."""
import re

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
        name="collect_contact_email",
        description=(
            "Save the customer's own email address (and name, if known) so the team can "
            "reply by email. Never pass an address that is not the customer's own."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "email": types.Schema(type=types.Type.STRING, description="The customer's email"),
                "name": types.Schema(type=types.Type.STRING, description="The customer's name, if known"),
            },
            required=["email"],
        ),
    ),
]

BOT_TOOLS = [types.Tool(function_declarations=DECLARATIONS)]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
            if name == "collect_contact_email":
                return self._collect_email(str(args.get("email", "")), args.get("name"))
            return {"error": f"unknown tool {name}"}
        except Exception as e:  # noqa: BLE001 — a tool failure must not crash the reply
            print(f"[tool] {name} failed: {e}")
            return {"error": "the action could not be completed right now"}

    def _escalate(self, reason: str, summary: str) -> dict:
        self.escalated = True
        if not self.dry_run and self.thread_id:
            db.update("threads", {"id": f"eq.{self.thread_id}", "tenant_id": f"eq.{self.tenant_id}"},
                      {"status": "escalated", "escalation_reason": reason[:300]})
            db.insert("messages", {
                "tenant_id": self.tenant_id, "thread_id": self.thread_id, "role": "system",
                "content": f"Escalated to the team: {reason}\n{summary}".strip()[:2000],
            })
        return {"escalated": True,
                "next": "Tell the customer that their request was passed to the team and someone will get back to them."}

    def _collect_email(self, email: str, name) -> dict:
        email = email.strip().lower()
        if not _EMAIL_RE.match(email):
            return {"saved": False, "reason": "invalid email address"}
        if not self.dry_run and self.contact_id:
            values = {"email": email}
            if isinstance(name, str) and name.strip():
                values["name"] = name.strip()[:120]
            db.update("contacts", {"id": f"eq.{self.contact_id}", "tenant_id": f"eq.{self.tenant_id}"}, values)
        return {"saved": True}
