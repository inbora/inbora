"""Zernio API: WhatsApp and Instagram for every business, through one Zernio
account (Inbora's). Each business gets its own Zernio profile, tagged with
externalId = our tenant id, so webhooks can be routed back to it."""
import hashlib
import hmac
import time
from typing import Any

import httpx

from . import db
from .config import get_settings

PLATFORMS = ("whatsapp", "instagram")

_client: httpx.Client | None = None


class ZernioError(Exception):
    def __init__(self, status: int, message: str, code: str = ""):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


def configured() -> bool:
    return bool(get_settings().zernio_api_key)


def client() -> httpx.Client:
    global _client
    if _client is None:
        s = get_settings()
        _client = httpx.Client(base_url=s.zernio_api_base.rstrip("/"), timeout=30,
                               headers={"Authorization": f"Bearer {s.zernio_api_key}"})
    return _client


def _call(method: str, path: str, *, retries: int = 1, **kw) -> dict[str, Any]:
    """One Zernio call. Retries once on a network error or a 5xx."""
    for attempt in range(retries + 1):
        try:
            res = client().request(method, path, **kw)
        except httpx.HTTPError as e:
            if attempt < retries:
                time.sleep(1.5)
                continue
            raise ZernioError(0, f"Zernio unreachable ({type(e).__name__})") from e
        if res.status_code >= 500 and attempt < retries:
            time.sleep(1.5)
            continue
        try:
            body = res.json() if res.content else {}
        except ValueError:
            body = {"error": res.text[:300]}
        if res.status_code >= 400:
            message = (body.get("error") or body.get("message") or res.text[:300]) if isinstance(body, dict) else res.text[:300]
            code = body.get("code", "") if isinstance(body, dict) else ""
            raise ZernioError(res.status_code, str(message), str(code))
        return body if isinstance(body, dict) else {"data": body}
    raise ZernioError(0, "Zernio call failed")


# ── Profiles: one per business, created the first time it connects a channel

def ensure_profile(tenant_id: str) -> str:
    tenant = db.select_one("tenants", {"select": "id,name,slug,zernio_profile_id", "id": f"eq.{tenant_id}"})
    if tenant is None:
        raise ZernioError(404, "Business not found")
    if tenant.get("zernio_profile_id"):
        return tenant["zernio_profile_id"]
    try:
        body = _call("POST", "/profiles", json={
            # Names must be unique in our Zernio team; the slug already is.
            "name": f"{tenant['name']} ({tenant['slug']})"[:100],
            "externalId": tenant_id,
            "description": "Inbora business",
        }, headers={"Idempotency-Key": f"profile-{tenant_id}"})
        profile_id = (body.get("profile") or {}).get("_id")
    except ZernioError as e:
        if e.status != 409:
            raise
        # Already exists (an earlier attempt that didn't get saved): reuse it.
        profile_id = None
        for p in (_call("GET", "/profiles").get("profiles") or []):
            if p.get("externalId") == tenant_id:
                profile_id = p.get("_id")
                break
        if not profile_id:
            raise
    if not profile_id:
        raise ZernioError(502, "Zernio did not return a profile id")
    db.update("tenants", {"id": f"eq.{tenant_id}"}, {"zernio_profile_id": profile_id})
    return profile_id


# ── Connecting accounts

def connect_url(platform: str, profile_id: str, redirect_url: str, *,
                whatsapp_app: bool = True, reconnect_account_id: str | None = None) -> str:
    params: dict[str, str] = {"profileId": profile_id, "redirect_url": redirect_url}
    if platform == "whatsapp":
        # business_app = the number keeps working in the WhatsApp Business app
        # (Meta "coexistence"); api = the number is used only through Inbora.
        params["onboarding"] = "business_app" if whatsapp_app else "api"
    elif platform == "instagram":
        params["loginMethod"] = "instagram_login"   # no Facebook Page needed
        if reconnect_account_id:
            params["reconnectAccountId"] = reconnect_account_id
    body = _call("GET", f"/connect/{platform}", params=params)
    url = body.get("authUrl")
    if not url:
        raise ZernioError(502, "Zernio did not return a connect link")
    return url


def find_account(profile_id: str, account_id: str) -> dict[str, Any] | None:
    """The account, if it really belongs to this profile (never trust the
    browser's redirect parameters on their own)."""
    body = _call("GET", "/accounts", params={"profileId": profile_id})
    for acc in body.get("accounts") or []:
        pid = acc.get("profileId")
        pid = pid.get("_id") if isinstance(pid, dict) else pid
        if acc.get("_id") == account_id and pid == profile_id:
            return acc
    return None


def delete_account(account_id: str) -> None:
    try:
        _call("DELETE", f"/accounts/{account_id}")
    except ZernioError as e:
        if e.status != 404:
            raise


# ── Sending

def send_message(conversation_id: str, account_id: str, text: str = "", *,
                 image_url: str | None = None, key: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"accountId": account_id, "message": text or ""}
    if image_url:
        payload["attachmentUrl"] = image_url
        payload["attachmentType"] = "image"
    headers = {"Idempotency-Key": key} if key else {}
    return _call("POST", f"/inbox/conversations/{conversation_id}/messages", json=payload, headers=headers)


def fetch_media(url: str) -> tuple[bytes, str] | None:
    """Download an attachment. WhatsApp media on zernio.com needs our API key;
    Instagram media is a public CDN link."""
    headers = {}
    if "zernio.com" in url and configured():
        headers["Authorization"] = f"Bearer {get_settings().zernio_api_key}"
    try:
        res = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
    except httpx.HTTPError as e:
        print(f"[zernio] media fetch failed: {e}")
        return None
    mime = res.headers.get("content-type", "").split(";")[0].strip()
    if res.status_code != 200 or not res.content:
        print(f"[zernio] media fetch {res.status_code} for {url[:80]}")
        return None
    return res.content, mime


# ── Webhooks

def verify_signature(raw_body: bytes, signature: str) -> bool:
    """X-Zernio-Signature: lowercase hex HMAC-SHA256 of the raw body."""
    secret = get_settings().zernio_webhook_secret
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip().lower())


def friendly_error(err: ZernioError, platform: str) -> str:
    """A delivery error the team can act on."""
    text = (err.message or "").lower()
    if any(k in text for k in ("24", "window", "re-engagement", "outside", "131047")):
        return ("window_closed: The customer hasn't written in the last 24 hours, so "
                f"{'WhatsApp' if platform == 'whatsapp' else 'Instagram'} doesn't allow a reply until they write again.")
    if err.status in (401, 403) or "disconnect" in text or "token" in text:
        return "disconnected: The account is disconnected. Reconnect it on the Channels page."
    return f"error: {err.message[:200] or 'Sending failed'}"
