"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

type Filter = "all" | "escalated" | "unread" | "bot";
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
};

type Message = {
  id: number;
  role: "user" | "assistant" | "human" | "system";
  content: string;
  created_at: string;
  author_name: string | null;
};

type Detail = {
  thread: ThreadRow & { channel_id: string };
  contact: { id: string; name: string | null; email: string | null; phone: string | null; external_id: string };
  channel: { id: string; type: ChannelType; mode: "auto" | "human" };
  messages: Message[];
};

const LIST_POLL_MS = 8000;
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
  const [counts, setCounts] = useState({ escalated: 0, unread: 0 });

  // Debounce the search box.
  useEffect(() => {
    const id = setTimeout(() => setQ(search.trim()), 300);
    return () => clearTimeout(id);
  }, [search]);

  const query = useCallback(
    (before?: string) => {
      const p = new URLSearchParams({ filter });
      if (channel) p.set("channel", channel);
      if (q) p.set("q", q);
      if (range === "custom") {
        if (dateFrom) p.set("date_from", dateFrom);
        if (dateTo) p.set("date_to", dateTo);
      } else if (range !== "any") p.set("days", range);
      if (before) p.set("before", before);
      return `/inbox/threads?${p}`;
    },
    [filter, channel, q, range, dateFrom, dateTo],
  );

  const refresh = useCallback(async () => {
    try {
      const [list, c] = await Promise.all([
        api<{ threads: ThreadRow[]; has_more: boolean }>(query()),
        api<{ escalated: number; unread: number }>("/inbox/counts"),
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

  const filtersActive = filter !== "all" || channel || q || range !== "any";

  return (
    <div className={`inbox${selected ? " inbox-has-thread" : ""}`}>
      <section className="inbox-list">
        <div className="inbox-tools">
          <div className="tabs" role="tablist">
            {(["all", "escalated", "unread", "bot"] as Filter[]).map((f) => (
              <button key={f} role="tab" aria-selected={filter === f}
                className={`tab${filter === f ? " tab-on" : ""}`} onClick={() => setFilter(f)}>
                {ti.filters[f]}
                {f === "escalated" && counts.escalated > 0 && <span className="count">{counts.escalated}</span>}
                {f === "unread" && counts.unread > 0 && <span className="count count-soft">{counts.unread}</span>}
              </button>
            ))}
          </div>
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
            <button key={th.id} className={`thread-row${th.id === selected ? " thread-row-on" : ""}${th.unread ? " thread-row-unread" : ""}`}
              onClick={() => open(th.id)}>
              <div className="thread-row-top">
                <span className="thread-name" dir="auto">{contactLabel(th, ti.visitor)}</span>
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
          ))}
          {hasMore && threads && threads.length > 0 && (
            <button className="link-btn load-more" onClick={loadMore}>{ti.loadMore}</button>
          )}
        </div>
      </section>

      <section className="inbox-thread">
        {selected ? (
          <ThreadView key={selected} id={selected} onBack={() => open(null)} onChanged={refresh}
            onRead={(unread) => markRead(selected, unread)} visible={visible} />
        ) : (
          <div className="thread-empty">{ti.pick}</div>
        )}
      </section>
    </div>
  );
}

function contactLabel(c: { contact_name?: string | null; contact_email?: string | null; contact_phone?: string | null; contact_external_id?: string }, visitor: string) {
  return c.contact_name || c.contact_email || c.contact_phone || `${visitor} ${(c.contact_external_id || "").slice(2, 6)}`;
}

function when(ts: string, lang: string) {
  const d = new Date(ts);
  const now = new Date();
  if (d.toDateString() === now.toDateString())
    return d.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString(lang, { day: "numeric", month: "short", ...(d.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}) });
}

function ThreadView({ id, onBack, onChanged, onRead, visible }: {
  id: string; onBack: () => void; onChanged: () => void; onRead: (unread: boolean) => void; visible: boolean;
}) {
  const { t, lang } = useI18n();
  const ti = t.inbox;
  const [data, setData] = useState<Detail | null>(null);
  const [missing, setMissing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"" | "send" | "draft" | "status">("");
  const [error, setError] = useState("");
  const [showDraft, setShowDraft] = useState(false);
  const [direction, setDirection] = useState("");
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
    if (!body || busy) return;
    setBusy("send");
    setError("");
    try {
      const r = await api<{ message: Message; delivered: boolean }>(`/inbox/threads/${id}/reply`, {
        method: "POST", body: JSON.stringify({ text: body }),
      });
      setText("");
      setShowDraft(false);
      setDirection("");
      if (!r.delivered) setError(ti.notDelivered);
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
        method: "POST", body: JSON.stringify({ direction: direction.trim() || null }),
      });
      setText(r.text);
    } catch {
      setError(ti.draftError);
    } finally {
      setBusy("");
    }
  }

  const name = contact.name || contact.email || contact.phone || `${ti.visitor} ${contact.external_id.slice(2, 6)}`;
  let lastDay = "";

  return (
    <div className="thread">
      <header className="thread-head">
        <button className="link-btn thread-back" onClick={onBack}>← {ti.back}</button>
        <div className="thread-who">
          <div className="thread-title" dir="auto">{name}</div>
          <div className="thread-sub">
            <span className={`chan chan-${channel.type}`}>{ti.channelNames[channel.type]}</span>
            {contact.email && name !== contact.email && <span dir="ltr">{contact.email}</span>}
            {contact.phone && name !== contact.phone && <span dir="ltr">{contact.phone}</span>}
          </div>
        </div>
        <div className="thread-actions">
          <button className="link-btn" onClick={markUnread}>{ti.markUnread}</button>
          {team ? (
            <button className="btn btn-secondary btn-sm" disabled={!!busy || channel.mode !== "auto"} onClick={() => act("handback")}>
              {ti.handback}
            </button>
          ) : (
            <button className="btn btn-sm" disabled={!!busy} onClick={() => act("takeover")}>{ti.takeover}</button>
          )}
        </div>
      </header>

      <div className={`thread-status ${team ? "thread-status-team" : ""}`}>
        <strong>{team ? ti.statusTeam : ti.statusBot}</strong>
        {team && thread.escalation_reason && <span> · {ti.reason}: <span dir="auto">{thread.escalation_reason}</span></span>}
        {team && channel.mode === "auto" && <span className="hint"> · {ti.handbackHint}</span>}
      </div>

      <div className="thread-log" ref={logRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}>
        {messages.map((m) => {
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
              <div className="msg-text" dir="auto">{m.content}</div>
              <div className="msg-time">{new Date(m.created_at).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" })}</div>
            </div>
          )];
        })}
      </div>

      <div className="composer">
        {showDraft && (
          <div className="draft-row">
            <input dir={direction ? "auto" : undefined} maxLength={1000} placeholder={ti.draftDirection} value={direction}
              onChange={(e) => setDirection(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); draft(); } }} />
            <button className="btn btn-secondary btn-sm" disabled={!!busy} onClick={draft}>
              {busy === "draft" ? ti.draftBusy : ti.draftWrite}
            </button>
          </div>
        )}
        <textarea dir={text ? "auto" : undefined} rows={3} maxLength={4000} placeholder={ti.replyPlaceholder} value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); }
          }} />
        <div className="composer-foot">
          <button className={`link-btn${showDraft ? " link-on" : ""}`} onClick={() => setShowDraft(!showDraft)}>✦ {ti.draft}</button>
          <span className="hint composer-hint">{error ? <span className="error-text">{error}</span> : !team && ti.replyTakesOver}</span>
          <button className="btn btn-sm" disabled={!text.trim() || !!busy} onClick={send}>{ti.send}</button>
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
