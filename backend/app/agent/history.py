"""Turns stored messages into the conversation history Gemini expects."""
import httpx
from google.genai import types

MAX_MESSAGES = 40
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _fetch_image(url: str) -> tuple[bytes, str] | None:
    headers = {}
    if "zernio.com" in url:
        from ..config import get_settings
        headers["Authorization"] = f"Bearer {get_settings().zernio_api_key}"
    try:
        res = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        mime = res.headers.get("content-type", "").split(";")[0].strip()
        if res.status_code == 200 and mime.startswith("image/") and len(res.content) <= MAX_IMAGE_BYTES:
            return res.content, mime
    except httpx.HTTPError as e:
        print(f"[history] image fetch failed: {e}")
    return None


def build(messages: list[dict]) -> list[types.Content]:
    """messages: oldest first, each {role, content, attachment_url?, attachment_mime?}.
    Customer messages become "user" turns; the agent's and the team's replies
    become "model" turns. System notes are skipped. Only the most recent
    customer image is sent as an image (cheap, and enough for context)."""
    msgs = [m for m in messages if m.get("role") in ("user", "assistant", "human")][-MAX_MESSAGES:]
    # Gemini wants the conversation to start with the customer.
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)

    last_img = -1
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if m["role"] == "user" and m.get("attachment_url") and (m.get("attachment_mime") or "").startswith("image/"):
            last_img = i
            break

    out: list[types.Content] = []
    for i, m in enumerate(msgs):
        parts: list[types.Part] = []
        if i == last_img:
            img = _fetch_image(m["attachment_url"])
            if img:
                parts.append(types.Part.from_bytes(data=img[0], mime_type=img[1]))
        text = (m.get("content") or "").strip()
        if not text and m.get("attachment_url") and i != last_img:
            text = "[the customer sent an attachment]"
        if text:
            parts.append(types.Part(text=text))
        if not parts:
            parts.append(types.Part(text=" "))
        out.append(types.Content(role="user" if m["role"] == "user" else "model", parts=parts))
    return out
