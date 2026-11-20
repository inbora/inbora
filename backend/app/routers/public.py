"""Public endpoints (no login): data-deletion requests from anyone whose data
a business holds in Inbora, and error reports from the panel in the browser."""
import html
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import db, errors
from ..config import get_settings

router = APIRouter(prefix="/public")

_LIMITS = {"deletion": (5, 3600), "client_error": (30, 600)}
_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _rate(bucket: str, request: Request) -> None:
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")
    limit, window = _LIMITS[bucket]
    now = time.time()
    with _lock:
        q = _hits[f"{bucket}:{ip}"]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Too many requests. Please try again later.")
        q.append(now)


class DeletionIn(BaseModel):
    contact: str = Field(min_length=3, max_length=200)      # email, phone or Instagram username
    name: str | None = Field(default=None, max_length=120)
    business: str | None = Field(default=None, max_length=200)
    details: str | None = Field(default=None, max_length=2000)


@router.post("/data-deletion")
def request_deletion(body: DeletionIn, request: Request):
    """Someone asks for the messages and details businesses hold about them
    in Inbora to be deleted. The super-admin checks and deletes them."""
    _rate("deletion", request)
    code = secrets.token_hex(4).upper()
    db.insert("deletion_requests", {"code": code, "contact": body.contact.strip(),
                                    "name": (body.name or "").strip() or None,
                                    "business": (body.business or "").strip() or None,
                                    "details": (body.details or "").strip() or None})
    threading.Thread(target=_notify, args=(code, body), daemon=True).start()
    return {"code": code}


def _notify(code: str, body: DeletionIn) -> None:
    from ..alerts import _send_email
    try:
        e = html.escape
        url = f"{get_settings().app_url.rstrip('/')}/admin?tab=deletion"
        _send_email(errors.admin_emails(), f"Data deletion request {code}", f"""<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
<h2 style="font-size:17px">Data deletion request {e(code)}</h2>
<p><b>Contact:</b> {e(body.contact)}<br><b>Name:</b> {e(body.name or '—')}<br><b>Business:</b> {e(body.business or '—')}</p>
<p>{e(body.details or '')}</p>
<p><a href="{e(url)}">Open the Super-admin page</a> to review and delete the data.</p></div>""")
    except Exception as ex:  # noqa: BLE001
        print(f"[public] could not email the deletion request: {ex}")


@router.get("/data-deletion/{code}")
def deletion_status(code: str):
    if not code.isalnum() or len(code) > 16:
        raise HTTPException(404, "Request not found")
    row = db.select_one("deletion_requests", {"select": "code,status,created_at,resolved_at",
                                              "code": f"eq.{code.upper()}"})
    if row is None:
        raise HTTPException(404, "Request not found")
    return row


class ClientError(BaseModel):
    message: str = Field(max_length=1000)
    page: str = Field(default="", max_length=300)
    stack: str | None = Field(default=None, max_length=8000)


@router.post("/client-error")
def client_error(body: ClientError, request: Request):
    """An error in the panel in someone's browser."""
    _rate("client_error", request)
    page = body.page.split("?")[0] or "?"
    errors.report("web", page, message=body.message, detail=body.stack)
    return {"ok": True}
