"""Billing: how a business moves to another plan.

Every payment provider implements BillingProvider. Until one is connected
(Paddle, for example), the manual provider is used: the business asks for a
plan from its Plan page, the super-admin gets an email, and assigns the plan
from the Super-admin page. Assigning a plan always goes through subscribe(),
which keeps a snapshot of the plan's limits and starts a fresh count."""
import html
from typing import Any, Protocol

from fastapi import HTTPException

from . import db, errors
from .config import get_settings


class BillingProvider(Protocol):
    name: str

    def create_checkout(self, tenant_id: str, plan: dict, user_id: str) -> dict[str, Any]:
        """Start moving to `plan`. Returns {"status": "requested"} (someone
        will act on it) or {"status": "redirect", "url": ...} (a checkout page)."""

    def cancel(self, tenant_id: str) -> None:
        """Stop the paid plan; the business goes back to the signup plan."""

    def handle_webhook(self, raw: bytes, headers: dict[str, str]) -> dict[str, Any]:
        """A payment event from the provider (paid, renewed, canceled...)."""


def subscribe(tenant_id: str, plan_id: str, provider: str = "manual", ref: str | None = None) -> str:
    """Put the business on a plan (ends the current subscription)."""
    return db.rpc("assign_plan", {"p_tenant": tenant_id, "p_plan": plan_id, "p_provider": provider, "p_ref": ref})


def signup_plan() -> dict | None:
    return db.select_one("plans", {"select": "*", "is_signup_default": "eq.true", "active": "eq.true"})


class ManualProvider:
    """No payments yet: requests go to the super-admin, who assigns the plan."""
    name = "manual"

    def create_checkout(self, tenant_id: str, plan: dict, user_id: str) -> dict[str, Any]:
        db.update("upgrade_requests", {"tenant_id": f"eq.{tenant_id}", "status": "eq.open"},
                  {"status": "dismissed"})          # one open request: the latest wins
        db.insert("upgrade_requests", {"tenant_id": tenant_id, "plan_id": plan["id"], "requested_by": user_id})
        self._notify(tenant_id, plan, user_id)
        return {"status": "requested"}

    def cancel(self, tenant_id: str) -> None:
        free = signup_plan()
        if free is None:
            raise HTTPException(500, "No signup plan is set")
        subscribe(tenant_id, free["id"], self.name)

    def handle_webhook(self, raw: bytes, headers: dict[str, str]) -> dict[str, Any]:
        raise HTTPException(404, "The manual provider has no webhook")

    @staticmethod
    def _notify(tenant_id: str, plan: dict, user_id: str) -> None:
        from .alerts import _send_email
        try:
            tenant = db.select_one("tenants", {"select": "name", "id": f"eq.{tenant_id}"}) or {}
            who = db.select_one("profiles", {"select": "email,full_name", "id": f"eq.{user_id}"}) or {}
            sub = db.select_one("subscriptions", {"select": "limits", "tenant_id": f"eq.{tenant_id}",
                                                  "status": "eq.active"}) or {}
            current = (sub.get("limits") or {}).get("plan_name", "—")
            e = html.escape
            url = f"{get_settings().app_url.rstrip('/')}/admin"
            body = f"""<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#14161a">
<h2 style="font-size:18px;margin:0 0 12px">Plan request: {e(tenant.get('name', ''))}</h2>
<p style="margin:0 0 6px"><b>From:</b> {e(who.get('full_name') or '')} {e(who.get('email') or '')}</p>
<p style="margin:0 0 14px"><b>{e(current)}</b> → <b>{e(plan['name'])}</b> (${e(str(plan.get('price_usd', '')))})</p>
<p><a href="{e(url)}" style="display:inline-block;background:#0e9f6e;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold">Open Super-admin</a></p></div>"""
            _send_email(errors.admin_emails(), f"Plan request: {tenant.get('name', '')} → {plan['name']}", body)
        except Exception as e:  # noqa: BLE001 — the request is saved either way
            print(f"[billing] could not email the request: {e}")


PROVIDERS: dict[str, BillingProvider] = {"manual": ManualProvider()}


def provider(name: str | None = None) -> BillingProvider:
    name = name or get_settings().billing_provider
    if name not in PROVIDERS:
        raise HTTPException(404, "Unknown billing provider")
    return PROVIDERS[name]
