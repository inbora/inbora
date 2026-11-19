"""Sending the agent's reply back out through the channel it came from.

The widget needs nothing: it fetches new messages itself (Step 4).
WhatsApp/Instagram (Zernio, Step 5) and email (Unipile, Step 6) plug in here."""


def deliver(channel: dict, thread: dict, contact: dict, text: str) -> None:
    kind = channel.get("type")
    if kind == "widget":
        return
    print(f"[deliver] sending on {kind} is not built yet (Steps 5–6); reply saved only")
