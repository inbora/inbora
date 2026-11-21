"""The plan's conversation quota.

A conversation is 24 hours from the first AI answer (or AI draft) in a
thread. Each new one counts once. When the plan's conversations are used up,
the agent stops answering new conversations — they go to the team instead —
until the next month or an upgrade. The team gets an email and a push at 80%
and at 100%."""
import html

from . import db, jobs
from .config import get_settings

OVER_REASON = "The plan's conversation limit is reached"
TRIAL_REASON = "The trial has ended"

TEXTS = {
    "en": {
        "80": "You've used 80% of your conversations",
        "100": "Your conversations are used up",
        "body_80": "{used} of {quota} conversations used on the {plan} plan. When they run out, the agent stops answering new conversations and they go to your team.",
        "body_100": "All {quota} conversations on the {plan} plan are used. The agent no longer answers new conversations; they go to your team in the Inbox. Upgrade to turn the agent back on.",
        "renews": "The count starts again on {date}.",
        "cta": "See plans",
    },
    "he": {
        "80": "ניצלתם 80% מהשיחות שלכם",
        "100": "השיחות שלכם נוצלו",
        "body_80": "נוצלו {used} מתוך {quota} שיחות בתוכנית {plan}. כשהן ייגמרו, הסוכן יפסיק לענות לשיחות חדשות והן יעברו לצוות שלכם.",
        "body_100": "כל {quota} השיחות בתוכנית {plan} נוצלו. הסוכן כבר לא עונה לשיחות חדשות; הן עוברות לצוות שלכם בתיבת הפניות. שדרגו כדי להפעיל את הסוכן מחדש.",
        "renews": "הספירה מתחילה מחדש ב-{date}.",
        "cta": "לתוכניות",
    },
    "ar": {
        "80": "استخدمت 80% من محادثاتك",
        "100": "نفدت محادثاتك",
        "body_80": "تم استخدام {used} من أصل {quota} محادثة في خطة {plan}. عندما تنفد، يتوقف الوكيل عن الرد على المحادثات الجديدة وتنتقل إلى فريقك.",
        "body_100": "تم استخدام كل المحادثات ({quota}) في خطة {plan}. لم يعد الوكيل يرد على المحادثات الجديدة؛ تنتقل إلى فريقك في صندوق الوارد. قم بالترقية لإعادة تشغيل الوكيل.",
        "renews": "يبدأ العدّ من جديد في {date}.",
        "cta": "عرض الخطط",
    },
}


def current(tenant_id: str) -> dict:
    """{status, used, quota, period_start, period_end} for the current period.
    status "unavailable" when counting isn't set up (migration 0009 not run)."""
    try:
        return db.rpc("current_usage", {"p_tenant": tenant_id}) or {"status": "no_plan"}
    except Exception as e:  # noqa: BLE001 — the panel keeps working without the count
        print(f"[usage] current_usage failed (is migration 0009 run?): {e}")
        return {"status": "unavailable"}


def consume(tenant_id: str, thread_id: str) -> dict:
    """Count this thread's conversation if it isn't counted yet. status:
    existing | new | over | no_plan | unavailable. Over = don't use the AI.
    If counting fails, customers are still answered (never blocked by a bug)."""
    try:
        res = db.rpc("consume_conversation", {"p_tenant": tenant_id, "p_thread": thread_id}) or {"status": "no_plan"}
    except Exception as e:  # noqa: BLE001
        print(f"[usage] consume_conversation failed (is migration 0009 run?): {e}")
        return {"status": "unavailable"}
    if res.get("alert"):
        try:
            jobs.enqueue("usage_alert", tenant_id, {"tenant_id": tenant_id, "level": int(res["alert"])})
        except Exception as e:  # noqa: BLE001 — never block a reply for an alert
            print(f"[usage] could not queue alert: {e}")
    return res


def allowed(res: dict) -> bool:
    return res.get("status") != "over"


def over_reason(res: dict) -> str:
    return TRIAL_REASON if res.get("trial_ended") else OVER_REASON


def record_tokens(tenant_id: str, tokens: dict | None) -> None:
    """Add the AI tokens one answer used to the business's current period."""
    if not tokens or not any(tokens.values()):
        return
    try:
        db.rpc("add_ai_usage", {"p_tenant": tenant_id, "p_input": int(tokens.get("input", 0)),
                                "p_cached": int(tokens.get("cached", 0)), "p_output": int(tokens.get("output", 0))})
    except Exception as e:  # noqa: BLE001
        print(f"[usage] could not record tokens: {e}")


def handle_usage_alert(payload: dict) -> str:
    from .alerts import _recipients, _send_email, _send_push
    tenant_id = payload.get("tenant_id")
    level = str(payload.get("level", 100))
    tenant = db.select_one("tenants", {"select": "id,name,default_language", "id": f"eq.{tenant_id}"})
    if tenant is None:
        return "tenant-gone"
    cur = current(tenant_id)
    sub = db.select_one("subscriptions", {"select": "limits", "tenant_id": f"eq.{tenant_id}", "status": "eq.active"}) or {}
    plan = (sub.get("limits") or {}).get("plan_name", "")
    people = _recipients(tenant_id)
    if not people:
        return "no-recipients"
    lang = tenant.get("default_language") or "en"
    t = TEXTS.get(lang, TEXTS["en"])
    title = t[level]
    body = t[f"body_{level}"].format(used=cur.get("used", 0), quota=cur.get("quota", 0), plan=plan)
    if cur.get("period_end") and (sub.get("limits") or {}).get("billing_period", "monthly") == "monthly":
        body += " " + t["renews"].format(date=str(cur["period_end"])[:10])
    url = f"{get_settings().app_url.rstrip('/')}/plan"
    direction = "rtl" if lang in ("he", "ar") else "ltr"
    e = html.escape
    color = "#c0352b" if level == "100" else "#14161a"
    body_html = f"""<div dir="{direction}" style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#14161a">
<h2 style="font-size:18px;margin:0 0 12px;color:{color}">{e(title)}</h2>
<p style="margin:0 0 14px">{e(body)}</p>
<p><a href="{e(url)}" style="display:inline-block;background:#0e9f6e;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold">{e(t['cta'])}</a></p></div>"""
    _send_email([p["email"] for p in people if p.get("email")], f"{title} — {tenant['name']}", body_html)
    pushed = _send_push([p["id"] for p in people], title, body[:180], url)
    return f"usage {level}% alert to {len(people)} people ({pushed} push)"
