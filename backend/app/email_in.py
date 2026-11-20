"""Email through Zernio: incoming mail, mail the team sent from their own
mailbox, and the poller that catches anything a webhook missed.

Every email is read in full (only the new text, without the quoted earlier
mail), filtered (newsletters, automatic mail, spam), and then handled like any
other customer message by inbound.receive_message(). The customer's email
address is the contact; the provider's message id is kept on the message so a
reply lands in the customer's own email thread."""
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

from . import db, inbound, jobs, zernio

# Folders and Gmail categories that never hold a customer writing to the business.
SKIP_FOLDERS = {"sent", "sent items", "sent mail", "sent messages", "draft", "drafts", "spam", "junk",
                "junk email", "trash", "bin", "deleted items", "deleted messages", "outbox",
                "category_promotions", "category_social", "category_forums"}
NO_REPLY = re.compile(r"^(no[-_.]?reply|do[-_.]?not[-_.]?reply|mailer-daemon|postmaster|bounces?)([+@-]|$)", re.I)
IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
POLL_OVERLAP = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Reading an email

class _Text(HTMLParser):
    BLOCKS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "table"}

    def __init__(self):
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self.skip += 1
        elif tag in self.BLOCKS:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCKS:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    try:
        p.feed(html or "")
    except Exception:  # noqa: BLE001 — broken html: keep what was read
        pass
    text = "".join(p.out).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _addr(a) -> tuple[str, str | None]:
    """(lower-case address, name) from {"email","name"} or "Name <a@b.c>"."""
    if isinstance(a, dict):
        return (a.get("email") or a.get("address") or "").strip().lower(), (a.get("name") or "").strip() or None
    if isinstance(a, str):
        m = re.match(r"\s*\"?([^\"<]*)\"?\s*<([^>]+)>", a)
        if m:
            return m.group(2).strip().lower(), m.group(1).strip() or None
        return a.strip().lower(), None
    return "", None


def _list(v) -> list:
    return v if isinstance(v, list) else ([v] if v else [])


def _headers(mail: dict) -> dict[str, str]:
    h = mail.get("headers") or {}
    if isinstance(h, list):        # [{"name","value"}] form
        h = {x.get("name", ""): x.get("value", "") for x in h if isinstance(x, dict)}
    return {str(k).lower(): str(v) for k, v in h.items()}


def _folders(mail: dict) -> set[str]:
    names = _list(mail.get("folders")) + _list(mail.get("labels")) + _list(mail.get("folder"))
    return {str(f).lower().removeprefix("[gmail]/").strip() for f in names if f}


def mailbox_address(channel: dict) -> str:
    cfg = channel.get("config") or {}
    return (cfg.get("email") or channel.get("display_name") or "").strip().lower()


def skip_reason(mail: dict, mailbox: str) -> str | None:
    """Why this email isn't from a customer, or None."""
    if _folders(mail) & SKIP_FOLDERS:
        return "folder"
    sender, _ = _addr(mail.get("from") or mail.get("sender"))
    if not sender or "@" not in sender:
        return "no-sender"
    if sender == mailbox:
        return "own-mail"
    h = _headers(mail)
    auto = h.get("auto-submitted", "").strip().lower()
    if auto and auto != "no":
        return "automatic"
    if h.get("precedence", "").strip().lower() in ("bulk", "list", "junk", "auto_reply"):
        return "bulk"
    if "list-unsubscribe" in h or "list-id" in h or "x-autoreply" in h or "x-autorespond" in h:
        return "newsletter"
    if NO_REPLY.match(sender.split("@")[0]):
        return "no-reply"
    return None


def customer_of(mail: dict, mailbox: str) -> tuple[str, str | None] | None:
    """The customer: the Reply-To address when there is one (website contact
    forms send from their own address with the customer as Reply-To),
    otherwise the sender."""
    for a in _list(mail.get("replyTo")):
        email, name = _addr(a)
        if "@" in email and email != mailbox:
            return email, name
    email, name = _addr(mail.get("from") or mail.get("sender"))
    if "@" in email and email != mailbox:
        if name and name.lower() == email:
            name = None
        return email, name
    return None


def body_text(mail: dict) -> str:
    clean = mail.get("clean") or {}
    text = (clean.get("text") or "").strip() if isinstance(clean, dict) else ""
    if not text:
        text = (mail.get("text") or "").strip() or html_to_text(mail.get("html") or "")
    return text[:8000]


def _attachments(mail: dict, account_id: str, message_id: str) -> tuple[str | None, str | None, list[str]]:
    """(first image url, its type, names of the other files)."""
    image_url = image_mime = None
    files: list[str] = []
    for att in _list(mail.get("attachments")):
        if not isinstance(att, dict) or att.get("isInline"):
            continue
        mime = (att.get("contentType") or "").split(";")[0].strip().lower()
        if (not image_url and mime in IMAGE_TYPES and att.get("id")
                and (att.get("size") or 0) <= MAX_IMAGE_BYTES):
            image_url = zernio.email_attachment_url(att["id"], account_id, message_id)
            image_mime = "image/jpeg" if mime == "image/jpg" else mime
        else:
            files.append(att.get("filename") or "file")
    return image_url, image_mime, files


# ── Incoming email

def _claim(channel: dict, message_id: str) -> str | None:
    """Mark this email as seen; None if it was already handled."""
    key = f"{channel['id']}:{message_id}"
    return key if db.rpc("mark_event_processed", {"p_provider": "email", "p_event_id": key}) else None


def _forget(key: str) -> None:
    db.delete("processed_events", {"provider": "eq.email", "event_id": f"eq.{key}"})


def _fetch(channel: dict, message_id: str, hint: dict | None) -> dict | None:
    try:
        return zernio.get_email(message_id, channel["external_account_id"])
    except zernio.ZernioError as e:
        if e.status == 404:
            return hint          # gone already: use what the webhook carried, if anything
        raise


def ingest(channel: dict, message_id: str, hint: dict | None = None) -> str:
    """A new email in the business's mailbox."""
    key = _claim(channel, message_id)
    if key is None:
        return "duplicate"
    try:
        mail = _fetch(channel, message_id, hint)
        if not mail:
            return "not-found"
        mailbox = mailbox_address(channel)
        if (_addr(mail.get("from") or mail.get("sender"))[0] or "") == mailbox and mailbox:
            return _record_sent(channel, message_id, mail)
        reason = skip_reason(mail, mailbox)
        if reason:
            return f"skipped: {reason}"
        who = customer_of(mail, mailbox)
        if who is None:
            return "skipped: no-customer"
        email, name = who
        account_id = channel["external_account_id"]
        text = body_text(mail)
        image_url, image_mime, files = _attachments(mail, account_id, message_id)
        if files:
            text = (text + "\n\n" if text else "") + "\n".join(f"📎 {f}" for f in files[:10])
        subject = (mail.get("subject") or "").strip() or None
        res = inbound.receive_message(
            channel, email, text, contact_name=name, contact_email=email,
            attachment_url=image_url, attachment_mime=image_mime,
            external_message_id=message_id, external_thread_id=mail.get("threadId"), subject=subject)
        if image_url:
            jobs.enqueue("media", channel["tenant_id"], {"message_id": res["message_id"], "url": image_url,
                                                         "thread_id": res["thread_id"]})
        return "stored+reply" if res["job_id"] else "stored"
    except Exception:
        _forget(key)
        raise


# ── Mail the team sent from their own mailbox (Gmail, Outlook...)

def sent_from_mailbox(channel: dict, message_id: str, hint: dict | None = None) -> str:
    key = _claim(channel, message_id)
    if key is None:
        return "duplicate"
    try:
        mail = _fetch(channel, message_id, hint)
        return _record_sent(channel, message_id, mail) if mail else "not-found"
    except Exception:
        _forget(key)
        raise


def _record_sent(channel: dict, message_id: str, mail: dict) -> str:
    """Show the team's own email in the conversation, if it went to a customer
    we know. Our own replies (sent through Inbora) are recognised and skipped."""
    if db.select_one("messages", {"select": "id", "tenant_id": f"eq.{channel['tenant_id']}",
                                  "external_id": f"eq.{message_id}", "limit": "1"}):
        return "own-send"
    recipients = [_addr(a)[0] for a in _list(mail.get("to")) + _list(mail.get("cc"))]
    recipients = [r for r in recipients if "@" in r]
    if not recipients:
        return "no-recipient"
    contact = db.select_one("contacts", {"select": "*", "channel_id": f"eq.{channel['id']}",
                                         "external_id": "in.(" + ",".join(f'"{r}"' for r in recipients) + ")",
                                         "limit": "1"})
    if contact is None:
        return "not-a-customer"
    thread = db.select_one("threads", {"select": "*", "channel_id": f"eq.{channel['id']}",
                                       "contact_id": f"eq.{contact['id']}"})
    if thread is None:
        return "not-a-customer"
    text = body_text(mail)
    since = (_now() - timedelta(minutes=10)).isoformat()
    recent = db.select("messages", {"select": "content", "thread_id": f"eq.{thread['id']}",
                                    "role": "in.(assistant,human)", "created_at": f"gte.{since}"})
    if text and any((r.get("content") or "").strip() == text.strip() for r in recent):
        return "own-send"            # our reply, before its id was saved
    now = _now().isoformat()
    db.insert("messages", {"tenant_id": channel["tenant_id"], "thread_id": thread["id"], "role": "human",
                           "content": text, "external_id": message_id,
                           **({"subject": mail["subject"][:300]} if mail.get("subject") else {})})
    values = {"last_message_at": now, "last_message_preview": (text or mail.get("subject") or "")[:140],
              "human_last_at": now, "archived_at": None}
    if thread["status"] != "escalated":
        values.update({"status": "escalated", "escalated_at": now,
                       "escalation_reason": "Answered from the mailbox"})
    db.update("threads", {"id": f"eq.{thread['id']}"}, values)
    db.rpc("bump_reply_epoch", {"p_thread": thread["id"]})
    return "team-reply"


# ── From the webhook

def hint_from_webhook(payload: dict) -> dict:
    """What a message.received / message.sent event carries, in the shape of
    an email, for when the full email can't be read."""
    msg = payload.get("message") or {}
    conv = payload.get("conversation") or {}
    sender = msg.get("sender") or {}
    address = sender.get("email") or sender.get("username") or conv.get("participantUsername") or ""
    name = sender.get("name") or sender.get("displayName") or conv.get("participantName")
    return {"id": msg.get("platformMessageId") or msg.get("id"),
            "threadId": msg.get("threadId") or (msg.get("metadata") or {}).get("threadId"),
            "from": {"email": address, "name": name},
            "subject": msg.get("subject") or conv.get("subject"),
            "text": msg.get("text") or "", "attachments": []}


def message_id_from_webhook(payload: dict) -> str | None:
    msg = payload.get("message") or {}
    return msg.get("platformMessageId") or msg.get("emailId") or msg.get("id")


# ── Poller: catches mail a webhook missed

def poll(channel: dict) -> str:
    account_id = channel.get("external_account_id")
    if not account_id:
        return "no-account"
    cfg = dict(channel.get("config") or {})
    since = cfg.get("email_since")
    if not since:
        cfg["email_since"] = _now().isoformat()
        db.update("channels", {"id": f"eq.{channel['id']}"}, {"config": cfg})
        return "started"
    since_dt = datetime.fromisoformat(str(since).replace("Z", "+00:00"))
    items = zernio.list_emails(account_id, after=(since_dt - POLL_OVERLAP).isoformat())
    mailbox = mailbox_address(channel)
    newest, handled = since_dt, 0
    for item in reversed(items):                     # oldest first
        mid = item.get("id")
        if not mid:
            continue
        sender = _addr(item.get("from") or item.get("sender"))[0]
        if mailbox and sender == mailbox:
            outcome = sent_from_mailbox(channel, mid)        # the team wrote from the mailbox
        elif _folders(item) & SKIP_FOLDERS:
            continue
        else:
            outcome = ingest(channel, mid)
        if outcome.startswith("stored") or outcome == "team-reply":
            handled += 1
        try:
            d = datetime.fromisoformat(str(item.get("date")).replace("Z", "+00:00"))
            newest = max(newest, d)
        except (TypeError, ValueError):
            pass
    if newest > since_dt:
        cfg["email_since"] = newest.isoformat()
        db.update("channels", {"id": f"eq.{channel['id']}"}, {"config": cfg})
    return f"{handled} new"


def poll_all() -> None:
    if not zernio.configured():
        return
    for ch in db.select("channels", {"select": "*,tenants(status)", "type": "eq.email", "status": "eq.connected"}):
        if (ch.pop("tenants", None) or {}).get("status") == "suspended":
            continue
        try:
            outcome = poll(ch)
            if outcome not in ("0 new", "started"):
                print(f"[email] poll {ch['id']}: {outcome}")
        except Exception as e:  # noqa: BLE001 — one mailbox failing never stops the others
            print(f"[email] poll {ch['id']} failed: {e}")
            from . import errors
            errors.report("email", "mailbox check", e, tenant_id=ch.get("tenant_id"))


# ── Moving a deleted conversation's emails to the mailbox's Trash

def handle_trash(payload: dict) -> str:
    account_id, ids = payload.get("account_id"), payload.get("message_ids") or []
    done = 0
    for mid in ids[:500]:
        try:
            zernio.trash_email(mid, account_id)
            done += 1
        except zernio.ZernioError as e:
            print(f"[email] trash {mid} failed: {e.status} {e.message}")
            if e.status in (401, 403):
                break
    return f"{done}/{len(ids)} moved to trash"
