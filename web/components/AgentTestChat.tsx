"use client";

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n/client";
import { createClient } from "@/lib/supabase/client";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

type Msg = { role: "user" | "assistant"; content: string; escalated?: boolean };

export default function AgentTestChat() {
  const { t } = useI18n();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [articles, setArticles] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [msgs, busy]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    const next: Msg[] = [...msgs, { role: "user", content: text }];
    setMsgs(next);
    setInput("");
    setBusy(true);
    setError("");
    // Give up after 75 s instead of showing "Typing…" forever.
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 75_000);
    try {
      const { data } = await createClient().auth.getSession();
      const res = await fetch(`${API_URL}/agent/test`, {
        method: "POST",
        signal: abort.signal,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${data.session?.access_token ?? ""}`,
        },
        // Only the last 30 messages, as the API allows.
        body: JSON.stringify({ messages: next.slice(-30).map(({ role, content }) => ({ role, content })) }),
      });
      if (!res.ok) {
        setError(res.status === 429 ? t.agentPage.rateLimited : res.status === 503 ? t.agentPage.unavailable : t.agentPage.error);
        return;
      }
      const body = await res.json();
      setArticles(body.articles);
      setMsgs([...next, { role: "assistant", content: body.reply, escalated: body.escalated }]);
    } catch (err) {
      setError(err instanceof DOMException && err.name === "AbortError" ? t.agentPage.timeout : t.agentPage.error);
    } finally {
      clearTimeout(timer);
      setBusy(false);
    }
  }

  return (
    <div className="card chat">
      <div className="chat-head">
        <h2>{t.agentPage.testTitle}</h2>
        {msgs.length > 0 && (
          <button type="button" className="link-btn" onClick={() => { setMsgs([]); setError(""); }}>
            {t.agentPage.reset}
          </button>
        )}
      </div>
      <p className="hint">{t.agentPage.testIntro}</p>
      <div className="chat-log">
        {msgs.map((m, i) => (
          <div key={i} className={`bubble ${m.role === "user" ? "bubble-user" : "bubble-bot"}`} dir="auto">
            {m.content}
            {m.escalated && <span className="bubble-tag">{t.agentPage.escalated}</span>}
          </div>
        ))}
        {busy && <div className="bubble bubble-bot bubble-typing">{t.agentPage.thinking}</div>}
        <div ref={endRef} />
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      <form className="chat-input" onSubmit={send}>
        <input dir="auto" value={input} maxLength={4000} placeholder={t.agentPage.placeholder}
          onChange={(e) => setInput(e.target.value)} />
        <button className="btn" disabled={busy || !input.trim()}>{t.agentPage.send}</button>
      </form>
      {articles !== null && (
        <div className="hint">{t.agentPage.articles}: {articles}</div>
      )}
    </div>
  );
}
