"""Sending a reply out through the channel the conversation came from.

The website chat needs nothing: the widget fetches new messages itself.
WhatsApp and Instagram go through Zernio. Email (Unipile) comes in Step 6."""
from .. import zernio


def deliver(channel: dict, thread: dict, contact: dict, text: str,
            image_url: str | None = None, key: str | None = None) -> str | None:
    """Send the message. Returns None when it went out, or a reason when it
    didn't (stored on the message so the inbox can show it)."""
    kind = channel.get("type")
    if kind == "widget":
        return None
    if kind in zernio.PLATFORMS:
        return _send_zernio(kind, channel, thread, text, image_url, key)
    print(f"[deliver] sending on {kind} is not built yet; reply saved only")
    return "error: This channel can't send replies yet."


def _send_zernio(kind: str, channel: dict, thread: dict, text: str,
                 image_url: str | None, key: str | None) -> str | None:
    if channel.get("status") == "error":
        return "disconnected: The account is disconnected. Reconnect it on the Channels page."
    conversation_id = thread.get("external_thread_id")
    account_id = channel.get("external_account_id")
    if not (conversation_id and account_id):
        return "error: This conversation can't be answered from Inbora (missing conversation link)."
    try:
        if image_url and text and kind == "instagram":
            # Instagram takes a photo or text per message, not both.
            zernio.send_message(conversation_id, account_id, image_url=image_url,
                                key=f"{key}-img" if key else None)
            zernio.send_message(conversation_id, account_id, text, key=key)
        else:
            # WhatsApp sends the text as the image's caption.
            zernio.send_message(conversation_id, account_id, text, image_url=image_url, key=key)
    except zernio.ZernioError as e:
        print(f"[deliver] {kind} send failed ({e.status}): {e.message}")
        return zernio.friendly_error(e, kind)
    return None
