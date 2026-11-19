"""Sending a reply out through the channel the conversation came from.

The website chat needs nothing: the widget fetches new messages itself.
WhatsApp, Instagram and email go through Zernio."""
from .. import db, zernio


def deliver(channel: dict, thread: dict, contact: dict, text: str,
            image_url: str | None = None, key: str | None = None) -> str | None:
    """Send the message. Returns None when it went out, or a reason when it
    didn't (stored on the message so the inbox can show it)."""
    kind = channel.get("type")
    if kind == "widget":
        return None
    if kind in zernio.PLATFORMS:
        return _send_zernio(kind, channel, thread, text, image_url, key)
    if kind == "email":
        return _send_email(channel, thread, contact, text, image_url, key)
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


_EXT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}


def _reply_subject(subject: str | None) -> str:
    subject = (subject or "").strip()
    if not subject:
        return "Re: your message"
    return subject if subject.lower().startswith(("re:", "aw:", "sv:", "תגובה:", "رد:")) else f"Re: {subject}"


def _send_email(channel: dict, thread: dict, contact: dict, text: str,
                image_url: str | None, key: str | None) -> str | None:
    """Answer in the customer's own email thread, from the business's mailbox."""
    if channel.get("status") == "error":
        return "disconnected: The mailbox is disconnected. Reconnect it on the Channels page."
    account_id = channel.get("external_account_id")
    address = (contact.get("email") or contact.get("external_id") or "").strip()
    if not account_id or "@" not in address:
        return "error: This conversation can't be answered from Inbora (no email address)."
    to = [{"email": address, **({"name": contact["name"]} if contact.get("name") else {})}]
    # Reply to the customer's latest email, so it stays in their thread.
    last = db.select_one("messages", {"select": "external_id,subject", "thread_id": f"eq.{thread['id']}",
                                      "role": "eq.user", "external_id": "not.is.null",
                                      "order": "id.desc", "limit": "1"})
    attachments = None
    if image_url:
        ext = image_url.rsplit(".", 1)[-1].lower() if "." in image_url.rsplit("/", 1)[-1] else "jpg"
        attachments = [{"filename": f"image.{ext}", "contentType": _EXT.get(ext, "image/jpeg"), "url": image_url}]
    subject = _reply_subject((last or {}).get("subject"))
    try:
        if last:
            sent = zernio.reply_email(last["external_id"], account_id, to, subject, text,
                                      attachments=attachments, key=key)
        else:
            sent = zernio.send_email(account_id, to, subject, text, attachments=attachments, key=key)
    except zernio.ZernioError as e:
        print(f"[deliver] email send failed ({e.status}): {e.message}")
        return zernio.friendly_error(e, "email")
    # Keep the sent email's id: it's how our own mail is recognised when the
    # mailbox reports it back, and how it can be moved to Trash later.
    sent_id = sent.get("id") if isinstance(sent, dict) else None
    if sent_id and key and key.startswith("msg-") and key[4:].isdigit():
        db.update("messages", {"id": f"eq.{key[4:]}"}, {"external_id": sent_id})
    return None
