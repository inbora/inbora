"""The public website chat. Anyone on the business's site can call these
endpoints, so they take only the widget key (public) and a random visitor id
the browser keeps, and they are rate-limited."""
import html
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .. import db, inbound, plans
from ..agent_defaults import default_for

router = APIRouter(prefix="/widget")

_JS_PATH = Path(__file__).resolve().parent.parent / "static" / "widget.js"
_VISITOR = re.compile(r"^v_[A-Za-z0-9]{16,48}$")
_KEY = re.compile(r"^wk_[A-Za-z0-9_-]{8,64}$")

# (limit, seconds) per bucket
_LIMITS = {"visitor": (12, 60), "ip": (30, 60), "key": (300, 600)}
_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _rate(bucket: str, ident: str) -> None:
    limit, window = _LIMITS[bucket]
    now = time.time()
    with _lock:
        q = _hits[f"{bucket}:{ident}"]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Too many messages. Please wait a moment.")
        q.append(now)
        if len(_hits) > 50_000:          # keep memory bounded
            for k in [k for k, v in _hits.items() if not v][:10_000]:
                _hits.pop(k, None)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


# Widget config changes rarely; cache it briefly so every poll isn't 3 queries.
_cache: dict[str, tuple[float, dict | None]] = {}
_CACHE_SECONDS = 30


def _load(key: str) -> dict:
    if not _KEY.match(key):
        raise HTTPException(404, "Unknown chat")
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CACHE_SECONDS:
        if hit[1] is None:
            raise HTTPException(404, "Unknown chat")
        return hit[1]
    ch = db.select_one("channels", {"select": "*", "widget_key": f"eq.{key}", "type": "eq.widget"})
    found = None
    if ch and ch["status"] == "connected":
        tenant = db.select_one("tenants", {"select": "name,default_language,status", "id": f"eq.{ch['tenant_id']}"})
        if tenant and tenant["status"] == "active":
            found = {"channel": ch, "tenant": tenant}
    _cache[key] = (time.time(), found)
    if found is None:
        raise HTTPException(404, "Unknown chat")
    return found


def _check_visitor(visitor_id: str) -> None:
    if not _VISITOR.match(visitor_id or ""):
        raise HTTPException(422, "Bad visitor id")


@router.get("/widget.js")
def widget_js():
    return Response(_JS_PATH.read_text(encoding="utf-8"), media_type="application/javascript",
                    headers={"Cache-Control": "public, max-age=300"})


@router.get("/{key}/config")
def config(key: str):
    w = _load(key)
    ch, tenant = w["channel"], w["tenant"]
    tid = ch["tenant_id"]
    lang = tenant.get("default_language") or "en"
    settings = db.select_one("agent_settings", {"select": "greeting", "tenant_id": f"eq.{tid}"}) or {}
    cfg = ch.get("config") or {}
    return {
        "name": tenant["name"],
        "language": lang,
        "greeting": (settings.get("greeting") or "").strip() or default_for(lang, "greeting"),
        "color": cfg.get("color", "#0e9f6e"),
        "position": cfg.get("position", "right"),
        "branding": bool(plans.limits(tid).get("show_branding", True)),
    }


class VisitorMessage(BaseModel):
    visitor_id: str = Field(max_length=60)
    text: str = Field(min_length=1, max_length=2000)
    page: str | None = Field(default=None, max_length=500)


def _contact_thread(channel: dict, visitor_id: str) -> tuple[dict | None, dict | None]:
    contact = db.select_one("contacts", {"select": "id", "channel_id": f"eq.{channel['id']}",
                                         "external_id": f"eq.{visitor_id}"})
    if not contact:
        return None, None
    thread = db.select_one("threads", {"select": "id,status,reply_epoch",
                                       "channel_id": f"eq.{channel['id']}", "contact_id": f"eq.{contact['id']}"})
    return contact, thread


@router.post("/{key}/messages")
async def post_message(key: str, request: Request):
    # The widget sends JSON as text/plain so browsers skip the CORS preflight.
    raw = await request.body()
    if len(raw) > 10_000:
        raise HTTPException(413, "Message too long")
    try:
        body = VisitorMessage.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Bad message")
    return await run_in_threadpool(_post, key, body, _client_ip(request))


def _post(key: str, body: VisitorMessage, ip: str) -> dict:
    w = _load(key)
    _check_visitor(body.visitor_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "Empty message")
    _rate("visitor", body.visitor_id)
    _rate("ip", ip)
    _rate("key", key)
    res = inbound.receive_message(w["channel"], body.visitor_id, text)
    msg = db.select_one("messages", {"select": "id,created_at", "id": f"eq.{res['message_id']}"}) or {}
    return {"id": res["message_id"], "created_at": msg.get("created_at"), "will_reply": bool(res["job_id"])}


def _typing(thread: dict | None, channel: dict, last: dict | None) -> bool:
    """The agent is (about to be) writing: it owns the thread and the customer
    wrote last, recently."""
    if not thread or thread["status"] != "bot" or channel.get("mode") != "auto" or not last:
        return False
    if last["role"] != "user":
        return False
    sent = datetime.fromisoformat(str(last["created_at"]).replace("Z", "+00:00"))
    return sent > datetime.now(timezone.utc) - timedelta(seconds=90)


@router.get("/{key}/messages")
def get_messages(key: str, visitor_id: str = Query(max_length=60), after: int = 0):
    """The visitor's conversation (or only messages newer than `after`)."""
    w = _load(key)
    _check_visitor(visitor_id)
    contact, thread = _contact_thread(w["channel"], visitor_id)
    if not thread:
        return {"messages": [], "typing": False, "team": False}
    params = {"select": "id,role,content,created_at", "thread_id": f"eq.{thread['id']}",
              "role": "in.(user,assistant,human)"}
    if after:
        params.update({"id": f"gt.{after}", "order": "id.asc", "limit": "100"})
        msgs = db.select("messages", params)
    else:
        params.update({"order": "id.desc", "limit": "100"})
        msgs = list(reversed(db.select("messages", params)))
    last = msgs[-1] if msgs else db.select_one("messages", {
        "select": "role,created_at", "thread_id": f"eq.{thread['id']}",
        "role": "in.(user,assistant,human)", "order": "id.desc", "limit": "1"})
    return {"messages": msgs, "typing": _typing(thread, w["channel"], last),
            "team": thread["status"] == "escalated"}


@router.get("/{key}/demo", response_class=HTMLResponse)
def demo(key: str, request: Request):
    """A plain test page with the chat on it, so the business can try it
    before adding it to their site."""
    w = _load(key)
    name = html.escape(w["tenant"]["name"])
    lang = w["tenant"].get("default_language") or "en"
    rtl = lang in ("he", "ar")
    base = str(request.base_url).rstrip("/")
    proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if proto and host:
        base = f"{proto}://{host}"
    title = {"en": "Website chat test page", "he": "דף בדיקה לצ׳אט באתר",
             "ar": "صفحة تجربة دردشة الموقع"}[lang]
    hint = {"en": "This is how the chat looks on your site. Click the button in the corner to try it.",
            "he": "כך הצ׳אט ייראה באתר שלכם. לחצו על הכפתור בפינה כדי לנסות.",
            "ar": "هكذا ستظهر الدردشة على موقعك. اضغط على الزر في الزاوية لتجربتها."}[lang]
    return f"""<!doctype html>
<html lang="{lang}" dir="{'rtl' if rtl else 'ltr'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>{name} · {title}</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;background:#f6f7f9;color:#14161a;margin:0;padding:48px 20px}}
main{{max-width:640px;margin:auto}}h1{{font-size:24px;margin:0 0 8px}}p{{color:#5d6470;line-height:1.6}}
.fake{{background:#fff;border:1px solid #e3e6ea;border-radius:12px;height:160px;margin-top:20px}}</style></head>
<body><main><h1>{name}</h1><p>{title}. {hint}</p><div class="fake"></div><div class="fake"></div></main>
<script src="{html.escape(base)}/widget/widget.js" data-key="{html.escape(key)}" async></script></body></html>"""
