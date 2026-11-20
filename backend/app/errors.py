"""Built-in error monitoring.

Every error is recorded in `error_events`, grouped (the same error is one
row with a count), and listed on the Super-admin page. The super-admin gets
an email the first time an error happens and at most once an hour after
that. Errors also stay in the Render logs as before."""
import hashlib
import html
import re
import threading
import traceback

from . import db
from .config import get_settings

_NUMBERS = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+", re.I)


def admin_emails() -> list[str]:
    rows = db.select("platform_admins", {"select": "email"})
    return [r["email"] for r in rows if r.get("email")]


def report(kind: str, where: str, exc: BaseException | None = None, *, message: str | None = None,
           detail: str | None = None, tenant_id: str | None = None) -> None:
    """Record an error (never raises). kind: api | job | delivery | web | email."""
    try:
        msg = (message or (f"{type(exc).__name__}: {exc}" if exc else "Error")).strip()[:1000]
        if detail is None and exc is not None:
            detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-8000:]
        # Same error with different ids or numbers = one group.
        fingerprint = hashlib.sha1(f"{kind}|{where}|{_NUMBERS.sub('#', msg)[:300]}".encode()).hexdigest()
        should_email = db.rpc("record_error", {"p_fingerprint": fingerprint, "p_kind": kind, "p_where": where,
                                               "p_message": msg, "p_detail": detail, "p_tenant": tenant_id})
        if should_email:
            threading.Thread(target=_email, args=(kind, where, msg, detail, tenant_id), daemon=True).start()
    except Exception as e:  # noqa: BLE001 — monitoring must never break the app
        print(f"[errors] could not record ({kind} {where}): {e}")


def _email(kind: str, where: str, msg: str, detail: str | None, tenant_id: str | None) -> None:
    from .alerts import _send_email
    try:
        business = ""
        if tenant_id:
            t = db.select_one("tenants", {"select": "name", "id": f"eq.{tenant_id}"}) or {}
            business = t.get("name") or ""
        e = html.escape
        url = f"{get_settings().app_url.rstrip('/')}/admin?tab=errors"
        body = f"""<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;color:#14161a">
<h2 style="font-size:17px;margin:0 0 10px;color:#c0352b">Inbora error: {e(kind)} · {e(where)}</h2>
{f'<p style="margin:0 0 8px"><b>Business:</b> {e(business)}</p>' if business else ''}
<p style="margin:0 0 12px"><b>{e(msg)}</b></p>
{f'<pre style="font-size:12px;background:#f6f7f9;padding:10px;border-radius:8px;white-space:pre-wrap">{e((detail or "")[-3000:])}</pre>' if detail else ''}
<p style="font-size:13px;color:#5d6470">You'll get at most one email an hour for this error.</p>
<p><a href="{e(url)}" style="display:inline-block;background:#0e9f6e;color:#fff;padding:9px 16px;border-radius:8px;text-decoration:none;font-weight:bold">See all errors</a></p></div>"""
        _send_email(admin_emails(), f"Inbora error: {kind} · {where}"[:150], body)
    except Exception as ex:  # noqa: BLE001
        print(f"[errors] could not email: {ex}")
