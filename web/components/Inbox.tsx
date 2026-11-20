"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

type Filter = "all" | "escalated";
type View = "inbox" | "archived";
type ChannelType = "widget" | "whatsapp" | "instagram" | "email";
type DateRange = "any" | "1" | "7" | "30" | "custom";

type ThreadRow = {
  id: string;
  status: "bot" | "escalated" | "closed";
  escalation_reason: string | null;
  unread: boolean;
  last_message_at: string;
  last_message_preview: string | null;
  channel_type: ChannelType;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  contact_external_id: string;
  contact_username?: string | null;
  archived_at?: string | null;
};

type Message = {
  id: number;
  role: "user" | "assistant" | "human" | "system";
  content: string;
  created_at: string;
  author_name: string | null;
  attachment_url?: string | null;
  attachment_mime?: string | null;
  delivery_error?: string | null;
  subject?: string | null;
};

/** "Re: Order #1001" and "Order #1001" are the same email subject. */
const baseSubject = (s?: string | null) => (s || "").replace(/^\s*((re|fwd?|aw|sv)\s*:\s*)+/i, "").trim().toLowerCase();

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

/** "window_closed: …" → the team-facing explanation in the panel language. */
function deliveryText(err: string, ti: { errWindow: string; errDisconnected: string; errOther: string }) {
  if (err.startsWith("window_closed:")) return ti.errWindow;
  if (err.startsWith("disconnected:")) return ti.errDisconnected;
  return `${ti.errOther}: ${err.replace(/^error:\s*/, "")}`;
}

type Detail = {
  thread: ThreadRow & { channel_id: string };
  contact: { id: string; name: string | null; email: string | null; phone: string | null; username?: string | null; external_id: string };
  channel: { id: string; type: ChannelType; mode: "auto" | "human" };
  messages: Message[];
};

const LIST_POLL_MS = 8000;
const DRAFT_OPEN_KEY = "inb_ai_draft_open";

/** Whether the AI draft box is open. Open by default; hiding or showing it is
    remembered in this browser (refresh, next day, every conversation). */
function useDraftOpen(): [boolean | null, (open: boolean) => void] {
  const [open, setOpen] = useState<boolean | null>(null);   // null until read, so it never flickers
  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem(DRAFT_OPEN_KEY); } catch { /* storage blocked: use the default */ }
    setOpen(saved !== "0");
  }, []);
  const set = (value: boolean) => {
    setOpen(value);
    try { localStorage.setItem(DRAFT_OPEN_KEY, value ? "1" : "0"); } catch { /* not remembered, still works */ }
  };
  return [open, set];
}
const THREAD_POLL_MS = 4000;

function useVisible() {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const on = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", on);
    return () => document.removeEventListener("visibilitychange", on);
  }, []);
  return visible;
}

export default function Inbox() {
  const { t, lang } = useI18n();
  const ti = t.inbox;
  const router = useRouter();
  const params = useSearchParams();
  const selected = params.get("thread");
  const visible = useVisible();

  const [filter, setFilter] = useState<Filter>("all");
  const [channel, setChannel] = useState<"" | ChannelType>("");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [range, setRange] = useState<DateRange>("any");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [threads, setThreads] = useState<ThreadRow[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [counts, setCounts] = useState({ escalated: 0, unread: 0, archived: 0 });
  const [view, setView] = useState<View>("inbox");
  const [menuFor, setMenuFor] = useState<string | null>(null);       // row whose ⋯ menu is open
  // The conversation to delete; email ones offer to move the emails to Trash too.
  const [confirmDelete, setConfirmDelete] = useState<{ id: string; email: boolean } | null>(null);
  const [trashToo, setTrashToo] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Close a row menu on any click outside it.
  useEffect(() => {
    if (!menuFor) return;
    const close = () => setMenuFor(null);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [menuFor]);

  // Debounce the search box.
  useEffect(() => {
    const id = setTimeout(() => setQ(search.trim()), 300);
    return () => clearTimeout(id);
  }, [search]);

  const query = useCallback(
    (before?: string) => {
      const p = new URLSearchParams({ filter: view === "archived" ? "archived" : filter });
      if (channel) p.set("channel", channel);
      if (q) p.set("q", q);
      if (range === "custom") {
        if (dateFrom) p.set("date_from", dateFrom);
        if (dateTo) p.set("date_to", dateTo);
      } else if (range !== "any") p.set("days", range);
      if (before) p.set("before", before);
      return `/inbox/threads?${p}`;
    },
    [view, filter, channel, q, range, dateFrom, dateTo],
  );

  const refresh = useCallback(async () => {
    try {
      const [list, c] = await Promise.all([
        api<{ threads: ThreadRow[]; has_more: boolean }>(query()),
        api<{ escalated: number; unread: number; archived: number }>("/inbox/counts"),
      ]);
      // Keep older pages the user already loaded.
      setThreads((prev) => {
        if (!prev || prev.length <= list.threads.length) return list.threads;
        const fresh = new Set(list.threads.map((x) => x.id));
        const oldest = list.threads.at(-1)?.last_message_at ?? "";
        return [...list.threads, ...prev.filter((x) => !fresh.has(x.id) && x.last_message_at < oldest)];
      });
      setHasMore((prev) => prev || list.has_more);
      setCounts(c);
    } catch {
      /* keep what we have; the next poll retries */
    }
  }, [query]);

  // New filters: start over.
  useEffect(() => {
    setThreads(null);
    setHasMore(false);
  }, [query]);

  useEffect(() => {
    if (!visible) return;
    refresh();
    const id = setInterval(refresh, LIST_POLL_MS);
    return () => clearInterval(id);
  }, [refresh, visible]);

  async function loadMore() {
    const last = threads?.at(-1);
    if (!last) return;
    const more = await api<{ threads: ThreadRow[]; has_more: boolean }>(query(last.last_message_at));
    setThreads([...(threads ?? []), ...more.threads.filter((x) => !threads?.some((y) => y.id === x.id))]);
    setHasMore(more.has_more);
  }

  const open = (id: string | null) => {
    const p = new URLSearchParams(params.toString());
    if (id) p.set("thread", id);
    else p.delete("thread");
    router.replace(`/inbox${p.size ? `?${p}` : ""}`, { scroll: false });
  };

  const markRead = (id: string, unread: boolean) =>
    setThreads((prev) => prev?.map((x) => (x.id === id ? { ...x, unread } : x)) ?? prev);

  const dropFromList = (id: string) => {
    setThreads((prev) => prev?.filter((x) => x.id !== id) ?? prev);
    if (selected === id) open(null);
  };

  async function setArchived(id: string, archived: boolean) {
    setMenuFor(null);
    await api(`/inbox/threads/${id}/archive`, { method: "POST", body: JSON.stringify({ archived }) });
    dropFromList(id);          // it moves to the other list
    refresh();
  }

  async function deleteThread() {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      const trash = confirmDelete.email && trashToo ? "?trash=true" : "";
      await api(`/inbox/threads/${confirmDelete.id}${trash}`, { method: "DELETE" });
      dropFromList(confirmDelete.id);
      setConfirmDelete(null);
      refresh();
    } finally {
      setDeleting(false);
    }
  }

  const filtersActive = filter !== "all" || channel || q || range !== "any";

  return (
    <div className={`inbox${selected ? " inbox-has-thread" : ""}`}>
      <section className="inbox-list">
        <div className="inbox-tools">
          {view === "archived" ? (
            <div className="archived-head">
              <button className="link-btn" onClick={() => { setView("inbox"); open(null); }}>← {ti.backToInbox}</button>
              <strong>🗄 {ti.archived}</strong>
            </div>
          ) : (
          <div className="tabs" role="tablist">
            {(["all", "escalated"] as Filter[]).map((f) => (
              <button key={f} role="tab" aria-selected={filter === f}
                className={`tab${filter === f ? " tab-on" : ""}`} onClick={() => setFilter(f)}>
                {ti.filters[f]}
                {f === "escalated" && counts.escalated > 0 && <span className="count">{counts.escalated}</span>}
              </button>
            ))}
          </div>
          )}
          <input className="search" type="search" dir={search ? "auto" : undefined} placeholder={ti.search}
            value={search} onChange={(e) => setSearch(e.target.value)} />
          <div className="inbox-selects">
            <select value={channel} onChange={(e) => setChannel(e.target.value as "" | ChannelType)} aria-label={ti.allChannels}>
              <option value="">{ti.allChannels}</option>
              {(["widget", "whatsapp", "instagram", "email"] as ChannelType[]).map((c) => (
                <option key={c} value={c}>{ti.channelNames[c]}</option>
              ))}
            </select>
            <select value={range} onChange={(e) => setRange(e.target.value as DateRange)} aria-label={ti.dates.any}>
              {(["any", "1", "7", "30", "custom"] as DateRange[]).map((r) => (
                <option key={r} value={r}>{ti.dates[r]}</option>
              ))}
            </select>
          </div>
          {range === "custom" && (
            <div className="inbox-selects">
              <label className="date-field">{ti.from}
                <input type="date" value={dateFrom} max={dateTo || undefined} onChange={(e) => setDateFrom(e.target.value)} />
              </label>
              <label className="date-field">{ti.to}
                <input type="date" value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} />
              </label>
            </div>
          )}
        </div>

        <div className="thread-list">
          {threads === null && <div className="list-note">…</div>}
          {threads?.length === 0 && <div className="list-note">{filtersActive ? ti.noMatch : ti.empty}</div>}
          {threads?.map((th) => (
            <div key={th.id} className={`thread-item${menuFor === th.id ? " thread-item-menu" : ""}`}>
            <button className={`thread-row${th.id === selected ? " thread-row-on" : ""}${th.unread ? " thread-row-unread" : ""}`}
              onClick={() => open(th.id)}>
              <div className="thread-row-top">
                <span className="thread-name">{(() => {
                  const who = identity(rowWho(th), th.channel_type, ti.visitor);
                  return <><bdi>{who.name}</bdi>{who.handle && <span className="handle" dir="ltr">{who.handle}</span>}</>;
                })()}</span>
                <span className="thread-time">{when(th.last_message_at, lang)}</span>
              </div>
              <div className="thread-row-bottom">
                <span className="thread-preview" dir="auto">{th.last_message_preview}</span>
                {th.unread && <span className="unread-dot" aria-label={ti.filters.unread} />}
              </div>
              <div className="thread-tags">
                <span className={`chan chan-${th.channel_type}`}>{ti.channelNames[th.channel_type]}</span>
                {th.status === "escalated" && <span className="tag-team">{ti.filters.escalated}</span>}
              </div>
            </button>
            <button className="row-more" aria-label={ti.moreActions} aria-haspopup="menu" aria-expanded={menuFor === th.id}
              onClick={(e) => { e.stopPropagation(); setMenuFor(menuFor === th.id ? null : th.id); }}>⋯</button>
            {menuFor === th.id && (
              <div className="row-menu" role="menu" onClick={(e) => e.stopPropagation()}>
                <button role="menuitem" onClick={() => setArchived(th.id, view !== "archived")}>
                  {view === "archived" ? `↩ ${ti.unarchive}` : `🗄 ${ti.archive}`}
                </button>
                <button role="menuitem" className="danger" onClick={() => { setMenuFor(null); setTrashToo(false); setConfirmDelete({ id: th.id, email: th.channel_type === "email" }); }}>
                  🗑 {ti.deleteConv}
                </button>
              </div>
            )}
            </div>
          ))}
          {hasMore && threads && threads.length > 0 && (
            <button className="link-btn load-more" onClick={loadMore}>{ti.loadMore}</button>
          )}
        </div>
        {view === "inbox" && (
          <div className="list-foot">
            <button className="link-btn" onClick={() => { setView("archived"); open(null); }}>
              🗄 {ti.archivedCount.replace("{n}", String(counts.archived))}
            </button>
          </div>
        )}
      </section>

      <section className="inbox-thread">
        {selected ? (
          <ThreadView key={selected} id={selected} onBack={() => open(null)} onChanged={refresh}
            onRead={(unread) => markRead(selected, unread)} visible={visible}
            onArchive={(archived) => setArchived(selected, archived)} onDelete={(email) => { setTrashToo(false); setConfirmDelete({ id: selected, email }); }} />
        ) : (
          <div className="thread-empty">{ti.pick}</div>
        )}
      </section>

      {confirmDelete && (
        <div className="modal-bg" role="presentation" onClick={() => !deleting && setConfirmDelete(null)}>
          <div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="del-title" onClick={(e) => e.stopPropagation()}>
            <h3 id="del-title">{ti.deleteTitle}</h3>
            <p>{ti.deleteBody}</p>
            {confirmDelete.email && (
              <label className="check del-trash">
                <input type="checkbox" checked={trashToo} disabled={deleting} onChange={(e) => setTrashToo(e.target.checked)} />
                {ti.deleteTrash}
              </label>
            )}
            <div className="actions">
              <button className="btn btn-secondary btn-sm" disabled={deleting} onClick={() => setConfirmDelete(null)}>{ti.cancel}</button>
              <button className="btn btn-sm btn-danger" disabled={deleting} onClick={deleteThread}>{ti.deleteConfirm}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

type Who = { name?: string | null; email?: string | null; phone?: string | null; username?: string | null; external_id?: string };

/** The customer's name (bold) and, next to it, how they're reached: their
    Instagram @username or WhatsApp number. Without a name, the @username /
    number / email becomes the main label. */
function identity(c: Who, channel: string, visitor: string): { name: string; handle: string | null } {
  const at = c.username ? `@${c.username.replace(/^@/, "")}` : null;
  const name = c.name || at || c.email || c.phone || `${visitor} ${(c.external_id || "").slice(2, 6)}`;
  let handle: string | null = null;
  if (channel === "instagram") handle = at;
  else if (channel === "whatsapp") handle = c.phone ?? null;
  else handle = c.email ?? null;
  return { name, handle: handle && handle !== name ? handle : null };
}

const rowWho = (th: ThreadRow): Who => ({ name: th.contact_name, email: th.contact_email, phone: th.contact_phone,
  username: th.contact_username, external_id: th.contact_external_id });

function when(ts: string, lang: string) {
  const d = new Date(ts);
  const now = new Date();
  if (d.toDateString() === now.toDateString())
    return d.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString(lang, { day: "numeric", month: "short", ...(d.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}) });
}

function ThreadView({ id, onBack, onChanged, onRead, visible, onArchive, onDelete }: {
  id: string; onBack: () => void; onChanged: () => void; onRead: (unread: boolean) => void; visible: boolean;
  onArchive: (archived: boolean) => void; onDelete: (email: boolean) => void;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  useEffect(() => {
    if (!moreOpen) return;
    const close = () => setMoreOpen(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [moreOpen]);
  const { t, lang } = useI18n();
  const ti = t.inbox;
  const [data, setData] = useState<Detail | null>(null);
  const [missing, setMissing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"" | "send" | "draft" | "status">("");
  const [error, setError] = useState("");
  const [draftOpen, setDraftOpen] = useDraftOpen();
  const [direction, setDirection] = useState("");
  const [undoText, setUndoText] = useState<string | null>(null);   // what the box held before the last draft
  const [image, setImage] = useState<{ base64: string; mime: string; preview: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function pickImage(file: File | undefined) {
    if (!file) return;
    if (file.size > MAX_IMAGE_BYTES) { setError(ti.imageTooBig); return; }
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result);
      setImage({ base64: url.split(",")[1] ?? "", mime: file.type || "image/jpeg", preview: url });
      setError("");
    };
    reader.readAsDataURL(file);
  }
  const logRef = useRef<HTMLDivElement>(null);
  const lastId = useRef(0);
  const stick = useRef(true);

  const scrollDown = () => requestAnimationFrame(() => {
    const el = logRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  });

  const load = useCallback(async () => {
    try {
      const d = await api<Detail>(`/inbox/threads/${id}`);
      setData(d);
      lastId.current = d.messages.at(-1)?.id ?? 0;
      onRead(false);
      stick.current = true;
      scrollDown();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setMissing(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Poll for new messages and status changes while the conversation is open.
  useEffect(() => {
    if (!visible || !data) return;
    const tick = async () => {
      try {
        const d = await api<Detail>(`/inbox/threads/${id}?after=${lastId.current}`);
        if (d.messages.length) {
          lastId.current = d.messages.at(-1)!.id;
          const el = logRef.current;
          stick.current = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          scrollDown();
        }
        setData((prev) => prev && {
          ...d,
          messages: [...prev.messages, ...d.messages.filter((m) => !prev.messages.some((p) => p.id === m.id))],
        });
      } catch { /* next tick */ }
    };
    const iv = setInterval(tick, THREAD_POLL_MS);
    return () => clearInterval(iv);
  }, [id, visible, data !== null]); // eslint-disable-line react-hooks/exhaustive-deps

  if (missing) return <div className="thread-empty">{ti.noMatch}</div>;
  if (!data) return <div className="thread-empty">…</div>;
  const { thread, contact, channel, messages } = data;
  const team = thread.status === "escalated";
  const archived = !!thread.archived_at;

  async function act(path: "takeover" | "handback") {
    setBusy("status");
    try {
      await api(`/inbox/threads/${id}/${path}`, { method: "POST" });
      const d = await api<Detail>(`/inbox/threads/${id}`);
      setData(d);
      lastId.current = d.messages.at(-1)?.id ?? lastId.current;
      scrollDown();
      onChanged();
    } finally {
      setBusy("");
    }
  }

  async function markUnread() {
    await api(`/inbox/threads/${id}/read`, { method: "POST", body: JSON.stringify({ unread: true }) });
    onRead(true);
    onBack();
  }

  async function send() {
    const body = text.trim();
    if ((!body && !image) || busy) return;
    setBusy("send");
    setError("");
    try {
      const r = await api<{ message: Message; delivered: boolean; error: string | null }>(`/inbox/threads/${id}/reply`, {
        method: "POST",
        body: JSON.stringify({ text: body, image: image ? { base64: image.base64, mime: image.mime } : null }),
      });
      setText("");
      setUndoText(null);
      setDirection("");
      setImage(null);
      // A delivery problem is shown on the message itself.
      const d = await api<Detail>(`/inbox/threads/${id}`);
      setData(d);
      lastId.current = d.messages.at(-1)?.id ?? lastId.current;
      stick.current = true;
      scrollDown();
      onChanged();
    } catch {
      setError(ti.sendError);
    } finally {
      setBusy("");
    }
  }

  async function draft() {
    setBusy("draft");
    setError("");
    try {
      const r = await api<{ text: string }>(`/inbox/threads/${id}/draft`, {
        method: "POST", body: JSON.stringify({ direction: direction.trim() || null, current_text: text.trim() || null }),
      });
      setUndoText(text);
      setText(r.text);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 402 ? ti.draftQuota : ti.draftError);
    } finally {
      setBusy("");
    }
  }

  const who = identity(contact, channel.type, ti.visitor);
  const name = who.name;
  const igUser = channel.type === "instagram" && contact.username ? contact.username.replace(/^@/, "") : null;
  let lastDay = "";
  let lastSubject = "";

  return (
    <div className="thread">
      <header className="thread-head">
        <button className="link-btn thread-back" onClick={onBack}>← {ti.back}</button>
        <div className="thread-who">
          <div className="thread-title">
            <bdi>{name}</bdi>
            {who.handle && (igUser
              ? <a className="handle" dir="ltr" href={`https://instagram.com/${encodeURIComponent(igUser)}`} target="_blank" rel="noopener noreferrer">{who.handle} ↗</a>
              : <span className="handle" dir="ltr">{who.handle}</span>)}
          </div>
          <div className="thread-sub">
            <span className={`chan chan-${channel.type}`}>{ti.channelNames[channel.type]}</span>
            {contact.email && name !== contact.email && who.handle !== contact.email && <span dir="ltr">{contact.email}</span>}
            {contact.phone && name !== contact.phone && who.handle !== contact.phone && <span dir="ltr">{contact.phone}</span>}
          </div>
        </div>
        <div className="thread-actions">
          {!archived && (
            <>
              <button className="link-btn" onClick={markUnread}>{ti.markUnread}</button>
              {team ? (
                <button className="btn btn-secondary btn-sm" disabled={!!busy || channel.mode !== "auto"} onClick={() => act("handback")}>
                  {ti.handback}
                </button>
              ) : (
                <button className="btn btn-sm" disabled={!!busy} onClick={() => act("takeover")}>{ti.takeover}</button>
              )}
            </>
          )}
          <span className="more-wrap">
            <button className="more-btn" aria-label={ti.moreActions} aria-haspopup="menu" aria-expanded={moreOpen}
              onClick={(e) => { e.stopPropagation(); setMoreOpen(!moreOpen); }}>⋯</button>
            {moreOpen && (
              <div className="row-menu head-menu" role="menu" onClick={(e) => e.stopPropagation()}>
                <button role="menuitem" onClick={() => { setMoreOpen(false); onArchive(!archived); }}>
                  {archived ? `↩ ${ti.unarchive}` : `🗄 ${ti.archive}`}
                </button>
                <button role="menuitem" className="danger" onClick={() => { setMoreOpen(false); onDelete(channel.type === "email"); }}>🗑 {ti.deleteConv}</button>
              </div>
            )}
          </span>
        </div>
      </header>

      {archived && <div className="thread-archived">🗄 {ti.archivedNote}</div>}
      {team && !archived && (
        <div className="thread-status thread-status-team">
          <strong>{ti.statusTeam}</strong>
          {thread.escalation_reason && <span> · {ti.reason}: <span dir="auto">{thread.escalation_reason}</span></span>}
        </div>
      )}

      <div className="thread-log" ref={logRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}>
        {messages.map((m) => {
          // An email's subject, shown when it changes (not on every reply).
          let subject: string | null = null;
          if (m.subject && baseSubject(m.subject) !== lastSubject) {
            subject = m.subject;
            lastSubject = baseSubject(m.subject);
          }
          const day = new Date(m.created_at).toDateString();
          const sep = day !== lastDay ? (lastDay = day, (
            <div key={`d${m.id}`} className="day-sep">{new Date(m.created_at).toLocaleDateString(lang, { weekday: "short", day: "numeric", month: "short" })}</div>
          )) : null;
          if (m.role === "system") {
            return [sep, <div key={m.id} className="note" dir="auto">{noteText(m.content, ti)}</div>];
          }
          const who = m.role === "user" ? name : m.role === "human" ? `${ti.team}${m.author_name ? ` · ${m.author_name}` : ""}` : ti.agent;
          return [sep, (
            <div key={m.id} className={`msg msg-${m.role}`}>
              <div className="msg-who">{who}</div>
              {m.attachment_url && (m.attachment_mime ?? "").startsWith("image/") && (
                <a href={m.attachment_url} target="_blank" rel="noopener noreferrer" className="msg-image">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={m.attachment_url} alt="" loading="lazy" />
                </a>
              )}
              {subject && <div className="msg-subject" dir="auto">{subject}</div>}
              {m.content && <div className="msg-text" dir="auto">{m.content}</div>}
              {m.delivery_error && <div className="msg-error">{deliveryText(m.delivery_error, ti)}</div>}
              <div className="msg-time">{new Date(m.created_at).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" })}</div>
            </div>
          )];
        })}
      </div>

      <div className="composer">
        {draftOpen === true && (
          <div className="draft-box">
            <div className="draft-top">
              <span className="draft-label">✦ {ti.draft}</span>
              <button className="icon-btn" title={ti.hideDraft} aria-label={ti.hideDraft} onClick={() => setDraftOpen(false)}>—</button>
            </div>
            <div className="draft-row">
              <input dir={direction ? "auto" : undefined} maxLength={1000} placeholder={ti.draftDirection} value={direction}
                onChange={(e) => setDirection(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); draft(); } }} />
            </div>
          </div>
        )}
        {image && (
          <div className="attach-preview">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={image.preview} alt="" />
            <button className="icon-btn" aria-label="×" onClick={() => setImage(null)}>×</button>
          </div>
        )}
        <textarea dir={text ? "auto" : undefined} rows={3} maxLength={4000} placeholder={ti.replyPlaceholder} value={text}
          onChange={(e) => { setText(e.target.value); setUndoText(null); }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); }
          }} />
        <div className="composer-foot">
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden
            onChange={(e) => { pickImage(e.target.files?.[0]); e.target.value = ""; }} />
          <button className="icon-btn attach-btn" title={ti.attach} aria-label={ti.attach} onClick={() => fileRef.current?.click()}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 11.5l-8.6 8.6a5 5 0 0 1-7.1-7.1l8.6-8.6a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l7.9-7.9" />
            </svg>
          </button>
          {draftOpen === false && (
            <button className="link-btn" onClick={() => setDraftOpen(true)}>✦ {ti.showDraft}</button>
          )}
          {undoText !== null && (
            <span className="undo">{ti.draftReplaced} · <button className="link-btn" onClick={() => { setText(undoText); setUndoText(null); }}>{ti.undo}</button></span>
          )}
          <span className="hint composer-hint">{error ? <span className="error-text">{error}</span> : !team && undoText === null && ti.replyTakesOver}</span>
          <button className="btn btn-sm ai-btn" disabled={!!busy} onClick={draft}>
            ✦ {busy === "draft" ? ti.draftBusy : ti.draftWrite}
          </button>
          <button className="btn btn-sm" disabled={(!text.trim() && !image) || !!busy} onClick={send}>{ti.send}</button>
        </div>
      </div>
    </div>
  );
}

function noteText(content: string, ti: { noteEscalated: string; noteTakeover: string; noteHandback: string; noteAutoHandback: string; reason: string }) {
  if (content.startsWith("Escalated to the team:")) {
    const [first, ...rest] = content.slice("Escalated to the team:".length).trim().split("\n");
    return `${ti.noteEscalated} · ${ti.reason}: ${first}${rest.length ? `\n${rest.join("\n")}` : ""}`;
  }
  if (content.startsWith("The team took over")) return ti.noteTakeover;
  if (content.startsWith("Handed back to the agent: no team reply")) return ti.noteAutoHandback;
  if (content.startsWith("Handed back to the agent")) return ti.noteHandback;
  return content;
}
