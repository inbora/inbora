"""Images in conversations, stored in Supabase Storage (bucket `inbora-media`).

WhatsApp media links need Inbora's Zernio key and Instagram links expire, so
images are copied here once, and the inbox, the agent and the customer's
channel all use the stored copy."""
import base64
import binascii
import uuid

import httpx

from .config import get_settings
from .db import _key_headers

BUCKET = "inbora-media"
MAX_BYTES = 5 * 1024 * 1024
TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}

_client: httpx.Client | None = None


class MediaError(Exception):
    pass


def client() -> httpx.Client:
    global _client
    if _client is None:
        s = get_settings()
        _client = httpx.Client(base_url=f"{s.supabase_base}/storage/v1", timeout=30,
                               headers=_key_headers(s.supabase_service_role_key.strip()))
    return _client


def public_url(path: str) -> str:
    return f"{get_settings().supabase_base}/storage/v1/object/public/{BUCKET}/{path}"


def upload(data: bytes, mime: str, tenant_id: str, thread_id: str) -> str:
    """Store an image and return its public URL."""
    mime = (mime or "").split(";")[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in TYPES:
        raise MediaError("Only JPG, PNG, WEBP or GIF images can be sent")
    if not data or len(data) > MAX_BYTES:
        raise MediaError("Images can be up to 5 MB")
    path = f"{tenant_id}/{thread_id}/{uuid.uuid4().hex}.{TYPES[mime]}"
    res = client().post(f"/object/{BUCKET}/{path}", content=data,
                        headers={"Content-Type": mime, "x-upsert": "false"})
    if res.status_code >= 300:
        raise MediaError(f"Storage {res.status_code}: {res.text[:200]}")
    return public_url(path)


def upload_base64(b64: str, mime: str, tenant_id: str, thread_id: str) -> str:
    if "," in b64[:100]:                      # tolerate a data: URL
        b64 = b64.split(",", 1)[1]
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise MediaError("The image could not be read")
    return upload(data, mime, tenant_id, thread_id)
