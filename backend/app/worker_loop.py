"""The background worker: takes jobs from the queue and runs them.

By default it runs inside the API process (EMBEDDED_WORKER=true), so no extra
Render service is needed. Later it can run on its own with `python worker.py`."""
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import alerts, channels, db, jobs, media, zernio
from .agent import context, history
from .agent import loop as agent_loop
from .agent.gemini import AgentUnavailable
from .agent.tools import Toolbox
from .config import get_settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def handle_reply(payload: dict) -> str:
    """Answer one thread. Returns what happened (for logs and tests)."""
    thread_id, epoch = payload["thread_id"], payload.get("epoch")
    thread = db.select_one("threads", {"select": "*", "id": f"eq.{thread_id}"})
    if thread is None:
        return "thread-gone"
    if epoch is not None and thread["reply_epoch"] != epoch:
        return "stale"            # a newer message arrived; its own job answers
    if thread["status"] != "bot":
        return "human"            # the team took over

    channel = db.select_one("channels", {"select": "*", "id": f"eq.{thread['channel_id']}"})
    if channel is None or channel.get("mode") != "auto":
        return "channel-manual"

    rows = db.select("messages", {
        "select": "role,content,attachment_url,attachment_mime",
        "thread_id": f"eq.{thread_id}", "order": "id.desc", "limit": str(history.MAX_MESSAGES),
    })
    rows.reverse()
    convo = [m for m in rows if m["role"] in ("user", "assistant", "human")]
    if not convo or convo[-1]["role"] != "user":
        return "already-answered"

    contact = db.select_one("contacts", {"select": "*", "id": f"eq.{thread['contact_id']}"}) or {}
    ctx = context.load(thread["tenant_id"])
    toolbox = Toolbox(thread["tenant_id"], thread_id=thread_id, contact_id=contact.get("id"))
    result = agent_loop.run(ctx, history.build(rows), toolbox,
                            channel=channel["type"], customer_name=contact.get("name"))

    # Re-check: did a newer message arrive, or a person take over, meanwhile?
    fresh = db.select_one("threads", {"select": "reply_epoch,status", "id": f"eq.{thread_id}"}) or {}
    if epoch is not None and fresh.get("reply_epoch") != epoch:
        return "stale"
    if fresh.get("status") == "escalated" and not result.escalated:
        return "human"
    if not result.text:
        return "empty"

    row = db.insert("messages", {"tenant_id": thread["tenant_id"], "thread_id": thread_id,
                                 "role": "assistant", "content": result.text})[0]
    db.update("threads", {"id": f"eq.{thread_id}"},
              {"last_message_at": _now(), "last_message_preview": result.text[:140]})
    error = channels.deliver(channel, thread, contact, result.text, key=f"msg-{row['id']}")
    if error:
        # The customer didn't get it: keep the reason and hand the thread to the team.
        db.update("messages", {"id": f"eq.{row['id']}"}, {"delivery_error": error})
        changed = db.update("threads", {"id": f"eq.{thread_id}", "status": "neq.escalated"},
                            {"status": "escalated", "escalated_at": _now(),
                             "escalation_reason": "The reply could not be delivered"})
        if changed:
            alerts.queue_alert(thread["tenant_id"], thread_id, "failed", error.split(": ", 1)[-1])
        return "undelivered"
    return "escalated" if result.escalated else "answered"


def handle_media(payload: dict) -> str:
    """Copy an image from WhatsApp / Instagram into our storage, so the inbox
    can show it and the link doesn't expire."""
    msg = db.select_one("messages", {"select": "id,tenant_id,thread_id,attachment_url",
                                     "id": f"eq.{payload['message_id']}"})
    if msg is None or msg.get("attachment_url") != payload.get("url"):
        return "gone-or-done"
    got = zernio.fetch_media(payload["url"])
    if got is None:
        raise RuntimeError("media download failed")
    data, mime = got
    try:
        url = media.upload(data, mime, msg["tenant_id"], msg["thread_id"])
    except media.MediaError as e:
        return f"skipped: {e}"
    db.update("messages", {"id": f"eq.{msg['id']}"}, {"attachment_url": url, "attachment_mime": mime})
    return "copied"


def _on_final_failure(job: dict, error: str) -> None:
    """Every attempt failed: hand the thread to the team so nobody waits forever."""
    if job.get("kind") != "reply":
        return
    tid = (job.get("payload") or {}).get("thread_id")
    if not tid:
        return
    try:
        changed = db.update("threads", {"id": f"eq.{tid}", "status": "eq.bot"},
                            {"status": "escalated", "escalated_at": _now(),
                             "escalation_reason": "The assistant could not answer (technical error)"})
        if changed:
            alerts.queue_alert(changed[0]["tenant_id"], tid, "failed", "technical error")
    except Exception as e:  # noqa: BLE001
        print(f"[worker] could not escalate thread {tid}: {e}")


HANDLERS = {"reply": handle_reply, "alert": alerts.handle_alert, "media": handle_media,
            "channel_alert": alerts.handle_channel_alert}


def process(job: dict) -> None:
    handler = HANDLERS.get(job["kind"])
    try:
        if handler is None:
            raise ValueError(f"unknown job kind {job['kind']}")
        outcome = handler(job.get("payload") or {})
        jobs.complete(job["id"])
        print(f"[worker] job {job['id']} {job['kind']}: {outcome}")
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
        if not isinstance(e, AgentUnavailable):
            traceback.print_exc()
        if not jobs.fail(job, error):
            print(f"[worker] job {job['id']} failed for good: {error}")
            _on_final_failure(job, error)
        else:
            print(f"[worker] job {job['id']} will retry: {error}")


def run_forever(stop: threading.Event | None = None) -> None:
    s = get_settings()
    stop = stop or threading.Event()
    last_purge = 0.0
    print(f"[worker] started (concurrency {s.worker_concurrency})", flush=True)
    with ThreadPoolExecutor(max_workers=s.worker_concurrency) as pool:
        while not stop.is_set():
            try:
                batch = jobs.claim(s.worker_concurrency)
            except Exception as e:  # noqa: BLE001 — database blip: wait and retry
                print(f"[worker] claim failed: {e}")
                stop.wait(5)
                continue
            if batch:
                list(pool.map(process, batch))
                continue
            if time.time() - last_purge > 3600:
                last_purge = time.time()
                try:
                    jobs.purge_finished()
                except Exception as e:  # noqa: BLE001
                    print(f"[worker] purge failed: {e}")
            stop.wait(1.0)


_stop = threading.Event()


def start_embedded() -> None:
    threading.Thread(target=run_forever, args=(_stop,), name="inbora-worker", daemon=True).start()


def stop_embedded() -> None:
    _stop.set()
