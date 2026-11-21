"""Billing: how a business moves to another plan.

Every payment provider implements BillingProvider. Until one is connected
(Paddle, for example), the manual provider is used: the business asks for a
plan from its Plan page, the super-admin gets an email, and assigns the plan
from the Super-admin page. Assigning a plan always goes through subscribe(),
which keeps a snapshot of the plan's limits and starts a fresh count."""
import html
from datetime import datetime, timedelta, timezone
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
        """Stop renewing; the plan runs to the end of the paid period."""

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
        """Nothing renews by itself yet: the super-admin handles it."""

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


# ── Custom plans: the business says what it needs, the super-admin sends a
# price, the business accepts and a private plan is made for it.

OFFER_DAYS = 14
_CUSTOM_FIELDS = "id,status,conversations,kb_chars,seats,notes,offer_price,offer_sent_at,offer_expires_at,created_at"

OFFER_TEXTS = {
    "en": {"subject": "Your Custom plan offer", "title": "Your Custom plan is ready",
           "body": "{conversations} AI conversations a month, {kb} characters of knowledge, {seats} team members, all channels: ${price} a month.",
           "expires": "The offer is valid until {date}.", "cta": "See the offer"},
    "he": {"subject": "הצעה לתוכנית מותאמת", "title": "התוכנית המותאמת שלכם מוכנה",
           "body": "{conversations} שיחות AI בחודש, {kb} תווי ידע, {seats} חברי צוות, כל הערוצים: ${price} לחודש.",
           "expires": "ההצעה בתוקף עד {date}.", "cta": "לצפייה בהצעה"},
    "ar": {"subject": "عرض خطة مخصّصة", "title": "خطتك المخصّصة جاهزة",
           "body": "{conversations} محادثة ذكاء اصطناعي شهريًا، {kb} حرفًا من المعرفة، {seats} أعضاء في الفريق، كل القنوات: ${price} شهريًا.",
           "expires": "العرض صالح حتى {date}.", "cta": "عرض التفاصيل"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None


def custom_view(row: dict | None) -> dict | None:
    if not row:
        return None
    exp = _parse(row.get("offer_expires_at"))
    return {**{k: row.get(k) for k in _CUSTOM_FIELDS.split(",")},
            "offer_price": float(row["offer_price"]) if row.get("offer_price") is not None else None,
            "expired": bool(row.get("status") == "offered" and exp and exp <= _now())}


def open_custom(tenant_id: str) -> dict | None:
    return db.select_one("custom_requests", {"select": _CUSTOM_FIELDS, "tenant_id": f"eq.{tenant_id}",
                                             "status": "in.(open,offered)", "order": "created_at.desc"})


def _email_admins(subject: str, lines: list[str]) -> None:
    from .alerts import _send_email
    try:
        e = html.escape
        url = f"{get_settings().app_url.rstrip('/')}/admin"
        body = "".join(f'<p style="margin:0 0 8px">{e(x)}</p>' for x in lines)
        _send_email(errors.admin_emails(), subject, f"""<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#14161a">
<h2 style="font-size:18px;margin:0 0 12px">{e(subject)}</h2>{body}
<p><a href="{e(url)}" style="display:inline-block;background:#0e9f6e;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold">Open Super-admin</a></p></div>""")
    except Exception as ex:  # noqa: BLE001 — saved either way
        print(f"[billing] could not email the super-admin: {ex}")


def request_custom(tenant_id: str, user_id: str, conversations: int, kb_chars: int, seats: int, notes: str) -> dict:
    db.update("custom_requests", {"tenant_id": f"eq.{tenant_id}", "status": "in.(open,offered)"},
              {"status": "dismissed", "resolved_at": _now().isoformat()})       # the latest request wins
    row = db.insert("custom_requests", {"tenant_id": tenant_id, "requested_by": user_id, "conversations": conversations,
                                        "kb_chars": kb_chars, "seats": seats, "notes": notes or None})[0]
    tenant = db.select_one("tenants", {"select": "name", "id": f"eq.{tenant_id}"}) or {}
    who = db.select_one("profiles", {"select": "email,full_name", "id": f"eq.{user_id}"}) or {}
    _email_admins(f"Custom plan request: {tenant.get('name', '')}", [
        f"From: {who.get('full_name') or ''} {who.get('email') or ''}",
        f"{conversations:,} AI conversations / month · {kb_chars:,} characters · {seats} team members",
        f"Special requests: {notes}" if notes else "No special requests."])
    return row


def send_offer(request_id: str, price: float) -> dict:
    row = db.select_one("custom_requests", {"select": "*", "id": f"eq.{request_id}", "status": "in.(open,offered)"})
    if row is None:
        raise HTTPException(404, "Request not found")
    now = _now()
    row = db.update("custom_requests", {"id": f"eq.{request_id}"}, {
        "status": "offered", "offer_price": round(price, 2), "offer_sent_at": now.isoformat(),
        "offer_expires_at": (now + timedelta(days=OFFER_DAYS)).isoformat()})[0]
    _email_offer(row)
    return row


def _email_offer(row: dict) -> None:
    from .alerts import _recipients, _send_email
    try:
        tenant = db.select_one("tenants", {"select": "name,default_language", "id": f"eq.{row['tenant_id']}"}) or {}
        lang = tenant.get("default_language") or "en"
        t = OFFER_TEXTS.get(lang, OFFER_TEXTS["en"])
        price = f"{float(row['offer_price']):g}"
        body = t["body"].format(conversations=f"{row['conversations']:,}", kb=f"{row['kb_chars']:,}",
                                seats=row["seats"], price=price)
        e = html.escape
        url = f"{get_settings().app_url.rstrip('/')}/plan"
        direction = "rtl" if lang in ("he", "ar") else "ltr"
        _send_email([p["email"] for p in _recipients(row["tenant_id"]) if p.get("email")],
                    f"{t['subject']} — {tenant.get('name', '')}",
                    f"""<div dir="{direction}" style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#14161a">
<h2 style="font-size:18px;margin:0 0 12px">{e(t['title'])}</h2><p style="margin:0 0 8px">{e(body)}</p>
<p style="margin:0 0 14px;color:#5b6470">{e(t['expires'].format(date=str(row['offer_expires_at'])[:10]))}</p>
<p><a href="{e(url)}" style="display:inline-block;background:#0e9f6e;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold">{e(t['cta'])}</a></p></div>""")
    except Exception as ex:  # noqa: BLE001
        print(f"[billing] could not email the offer: {ex}")


def accept_offer(tenant_id: str, request_id: str) -> dict:
    """A private plan with the offered terms; the business moves to it."""
    row = db.select_one("custom_requests", {"select": "*", "id": f"eq.{request_id}", "tenant_id": f"eq.{tenant_id}",
                                            "status": "eq.offered"})
    if row is None:
        raise HTTPException(404, "Offer not found")
    if custom_view(row)["expired"]:
        raise HTTPException(410, detail={"code": "offer_expired"})
    n = len(db.select("plans", {"select": "id", "code": f"like.custom-{tenant_id[:8]}-*"})) + 1
    plan = db.insert("plans", {
        "code": f"custom-{tenant_id[:8]}-{n}", "name": "Custom", "price_usd": row["offer_price"],
        "billing_period": "monthly", "conversation_quota": row["conversations"], "max_channels": 4,
        "kb_char_limit": row["kb_chars"], "seats": row["seats"], "show_branding": False,
        "is_public": False, "active": True, "sort_order": 100})[0]
    subscribe(tenant_id, plan["id"], "manual")
    db.update("custom_requests", {"id": f"eq.{request_id}"},
              {"status": "accepted", "plan_id": plan["id"], "resolved_at": _now().isoformat()})
    tenant = db.select_one("tenants", {"select": "name", "id": f"eq.{tenant_id}"}) or {}
    _email_admins(f"Custom offer accepted: {tenant.get('name', '')}", [
        f"${float(row['offer_price']):g} / month — {row['conversations']:,} conversations, "
        f"{row['kb_chars']:,} characters, {row['seats']} team members.",
        "They're on the new plan now. Arrange the payment with them."])
    return plan
