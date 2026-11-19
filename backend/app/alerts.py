"""Tell the business's team when a conversation needs them: by email (Resend)
and by browser push. Alerts are queued as jobs, so a slow email server never
delays a reply to a customer."""
import html
import json
from datetime import datetime, timedelta, timezone

import httpx

from . import db, jobs
from .config import get_settings

# A customer who keeps writing while the team handles the conversation
# triggers at most one alert per thread in this window.
REPEAT_WINDOW = timedelta(minutes=10)

TEXTS = {
    "en": {
        "escalated": "A conversation needs your team",
        "customer_message": "New message in a conversation you're handling",
        "failed": "The assistant couldn't answer a conversation",
        "open": "Open in Inbora",
        "visitor": "Website visitor",
        "from": "From",
        "reason": "Reason",
        "channel": {"widget": "Website chat", "whatsapp": "WhatsApp", "instagram": "Instagram", "email": "Email"},
        "footer": "You get this because you're on the team of {business} in Inbora.",
    },
    "he": {
        "escalated": "שיחה ממתינה לצוות שלכם",
        "customer_message": "הודעה חדשה בשיחה שאתם מטפלים בה",
        "failed": "הסוכן לא הצליח לענות בשיחה",
        "open": "פתיחה ב-Inbora",
        "visitor": "מבקר באתר",
        "from": "מאת",
        "reason": "סיבה",
        "channel": {"widget": "צ׳אט באתר", "whatsapp": "וואטסאפ", "instagram": "אינסטגרם", "email": "מייל"},
        "footer": "קיבלתם את ההודעה כי אתם בצוות של {business} ב-Inbora.",
    },
    "ar": {
        "escalated": "محادثة بانتظار فريقك",
        "customer_message": "رسالة جديدة في محادثة تتولاها",
        "failed": "لم يتمكن الوكيل من الرد على محادثة",
        "open": "فتح في Inbora",
        "visitor": "زائر الموقع",
        "from": "من",
        "reason": "السبب",
        "channel": {"widget": "دردشة الموقع", "whatsapp": "واتساب", "instagram": "إنستغرام", "email": "البريد"},
        "footer": "وصلتك هذه الرسالة لأنك ضمن فريق {business} في Inbora.",
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(v) -> datetime | None:
    return datetime.fromisoformat(str(v).replace("Z", "+00:00")) if v else None


def queue_alert(tenant_id: str, thread_id: str, kind: str, detail: str = "") -> None:
    """kind: escalated | customer_message | failed. Never raises: a failed alert
    must not break the reply flow."""
    try:
        if kind == "customer_message":
            # Skip if the team was already alerted in the last few minutes and
            # hasn't replied since (a reply means they're waiting for news).
            t = db.select_one("threads", {"select": "notified_at,human_last_at", "id": f"eq.{thread_id}"}) or {}
            last, replied = _ts(t.get("notified_at")), _ts(t.get("human_last_at"))
            if last and last > _now() - REPEAT_WINDOW and not (replied and replied > last):
                return
        db.update("threads", {"id": f"eq.{thread_id}"}, {"notified_at": _now().isoformat()})
        jobs.enqueue("alert", tenant_id, {"thread_id": thread_id, "kind": kind, "detail": detail[:300]})
    except Exception as e:  # noqa: BLE001
        print(f"[alerts] could not queue alert for {thread_id}: {e}")


def _recipients(tenant_id: str) -> list[dict]:
    members = db.select("tenant_members", {"select": "user_id", "tenant_id": f"eq.{tenant_id}"})
    if not members:
        return []
    ids = ",".join(m["user_id"] for m in members)
    return db.select("profiles", {"select": "id,email,preferred_language", "id": f"in.({ids})"})


def _send_email(to: list[str], subject: str, body_html: str) -> None:
    s = get_settings()
    if not s.resend_api_key or not to:
        return
    res = httpx.post("https://api.resend.com/emails", timeout=20,
                     headers={"Authorization": f"Bearer {s.resend_api_key}"},
                     json={"from": s.alerts_from, "to": to, "subject": subject, "html": body_html})
    if res.status_code >= 300:
        raise RuntimeError(f"Resend {res.status_code}: {res.text[:200]}")


def _send_push(user_ids: list[str], title: str, body: str, url: str) -> int:
    s = get_settings()
    if not (s.vapid_public_key and s.vapid_private_key) or not user_ids:
        return 0
    from pywebpush import WebPushException, webpush
    subs = db.select("push_subscriptions", {"select": "id,endpoint,p256dh,auth",
                                            "user_id": f"in.({','.join(user_ids)})"})
    sent = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=json.dumps({"title": title, "body": body, "url": url}),
                vapid_private_key=s.vapid_private_key,
                vapid_claims={"sub": s.vapid_subject},
                ttl=12 * 3600,          # still delivered if the device wakes up within 12 hours
                timeout=10,
            )
            sent += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):          # the browser unsubscribed: forget it
                db.delete("push_subscriptions", {"id": f"eq.{sub['id']}"})
            else:
                print(f"[alerts] push failed ({code}): {e}")
    return sent


def handle_alert(payload: dict) -> str:
    thread = db.select_one("threads", {"select": "*", "id": f"eq.{payload['thread_id']}"})
    if thread is None:
        return "thread-gone"
    tenant = db.select_one("tenants", {"select": "name,default_language", "id": f"eq.{thread['tenant_id']}"}) or {}
    contact = db.select_one("contacts", {"select": "name,email,phone,external_id", "id": f"eq.{thread['contact_id']}"}) or {}
    channel = db.select_one("channels", {"select": "type", "id": f"eq.{thread['channel_id']}"}) or {}
    people = _recipients(thread["tenant_id"])
    if not people:
        return "no-recipients"

    lang = tenant.get("default_language") or "en"
    t = TEXTS.get(lang, TEXTS["en"])
    kind = payload.get("kind", "escalated")
    title = t.get(kind, t["escalated"])
    who = (contact.get("name") or contact.get("email") or contact.get("phone")
           or (t["visitor"] if channel.get("type") == "widget" else contact.get("external_id")) or "—")
    where = t["channel"].get(channel.get("type", ""), channel.get("type", ""))
    preview = thread.get("last_message_preview") or ""
    url = f"{get_settings().app_url.rstrip('/')}/inbox?thread={thread['id']}"
    detail = payload.get("detail") or thread.get("escalation_reason") or ""

    direction = "rtl" if lang in ("he", "ar") else "ltr"
    e = html.escape
    body_html = f"""<div dir="{direction}" style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#14161a">
<h2 style="font-size:18px;margin:0 0 12px">{e(title)}</h2>
<p style="margin:0 0 6px"><b>{e(t['from'])}:</b> {e(who)} · {e(where)}</p>
{f'<p style="margin:0 0 6px"><b>{e(t["reason"])}:</b> {e(detail)}</p>' if detail else ''}
<blockquote style="margin:12px 0;padding:10px 14px;background:#f6f7f9;border-radius:8px">{e(preview)}</blockquote>
<p><a href="{e(url)}" style="display:inline-block;background:#0e9f6e;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold">{e(t['open'])}</a></p>
<p style="color:#5d6470;font-size:12px">{e(t['footer'].format(business=tenant.get('name', '')))}</p></div>"""

    _send_email([p["email"] for p in people if p.get("email")], f"{title} — {who}", body_html)
    pushed = _send_push([p["id"] for p in people], title, f"{who}: {preview}"[:180], url)
    return f"alerted {len(people)} people ({pushed} push)"
