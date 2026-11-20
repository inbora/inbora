"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

type Suggestion = { title: string; body: string; source: string | null; exists: boolean };
type Import = {
  id: string; url: string; status: "queued" | "reading" | "writing" | "ready" | "failed";
  pages_done: number; pages_total: number; pages_read: number; suggestions: Suggestion[]; error: string | null;
};
type Item = Suggestion & { keep: boolean; editing: boolean };

const RUNNING = ["queued", "reading", "writing"];
const host = (u: string) => u.replace(/^https?:\/\//, "").replace(/\/$/, "");

/** Knowledge from the business's website: address → reading → review → add. */
export default function SiteImport({ open, onClose, onAdded, onVisible, used, limit }: {
  open: boolean; onClose: () => void; onAdded: () => Promise<void>; onVisible: (v: boolean) => void;
  used: number; limit: number;
}) {
  const { t, lang } = useI18n();
  const k = t.knowledge;
  const nf = useMemo(() => new Intl.NumberFormat(lang), [lang]);
  const [imp, setImp] = useState<Import | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [url, setUrl] = useState("");
  const [language, setLanguage] = useState<string>(lang);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [asking, setAsking] = useState(false);     // address form reopened after a failed import

  const show = useCallback((i: Import | null) => {
    setImp(i);
    if (i?.status === "ready") setItems(i.suggestions.map((s) => ({ ...s, keep: true, editing: false })));
  }, []);

  // An import still running or waiting for review comes back when the page opens.
  useEffect(() => {
    api<{ import: Import | null; website: string }>("/knowledge/import")
      .then((r) => { show(r.import); setUrl((u) => u || r.website); })
      .catch(() => {});
  }, [show]);

  const running = !!imp && RUNNING.includes(imp.status);
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => {
      api<{ import: Import | null }>("/knowledge/import").then((r) => show(r.import)).catch(() => {});
    }, 2000);
    return () => clearInterval(timer);
  }, [running, show]);

  const visible = open || asking || !!imp;
  useEffect(() => onVisible(visible), [visible, onVisible]);

  async function start(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api<{ import: Import }>("/knowledge/import", { method: "POST", body: JSON.stringify({ url, language }) });
      show(r.import);
    } catch (err) {
      const d = err instanceof ApiError ? (err.detail as { code?: string; limit?: number } | null) : null;
      setError(d?.code === "bad_url" ? k.importBadUrl
        : d?.code === "import_limit" ? k.importLimit.replace("{n}", nf.format(d.limit ?? 5)) : k.error);
    } finally {
      setBusy(false);
    }
  }

  async function close() {
    if (imp) await api(`/knowledge/import/${imp.id}`, { method: "DELETE" }).catch(() => {});
    setImp(null);
    setError("");
    setAsking(false);
    onClose();
  }

  const kept = items.filter((i) => i.keep);
  const size = kept.reduce((n, i) => n + i.title.trim().length + i.body.trim().length, 0);
  const left = limit - used - size;

  async function add() {
    if (!imp) return;
    setBusy(true);
    setError("");
    try {
      await api(`/knowledge/import/${imp.id}/apply`, {
        method: "POST", body: JSON.stringify({ articles: kept.map(({ title, body }) => ({ title, body })) }),
      });
      setImp(null);
      setAsking(false);
      onClose();
      await onAdded();
    } catch {
      setError(k.error);
    } finally {
      setBusy(false);
    }
  }

  const edit = (n: number, patch: Partial<Item>) => setItems(items.map((it, i) => (i === n ? { ...it, ...patch } : it)));

  if (!visible) return null;

  // Address
  if (!imp) {
    return (
      <form className="card" onSubmit={start}>
        <h2>{k.importTitle}</h2>
        <p className="hint">{k.importHint}</p>
        <div className="imp-row">
          <input dir="ltr" aria-label={k.importAddress} placeholder="yourshop.com" value={url} autoFocus
            onChange={(e) => { setUrl(e.target.value); setError(""); }} />
          <label className="inline-field">
            {k.templateLanguage}
            <select className="lang" value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="en">English</option>
              <option value="he">עברית</option>
              <option value="ar">العربية</option>
            </select>
          </label>
        </div>
        {error && <p className="error-text">{error}</p>}
        <div className="actions">
          <span className="spacer" />
          <button type="button" className="btn btn-secondary" onClick={close}>{k.cancel}</button>
          <button className="btn" disabled={busy || url.trim().length < 3}>{k.importStart}</button>
        </div>
      </form>
    );
  }

  // Reading / writing
  if (running) {
    const pct = imp.status === "writing" ? 100 : imp.pages_total ? Math.round((imp.pages_done / imp.pages_total) * 100) : 5;
    return (
      <div className="card">
        <h2>{k.importTitle}</h2>
        <p className="hint" dir="ltr">{host(imp.url)}</p>
        <div className="meter imp-meter"><span style={{ width: `${pct}%` }} /></div>
        <div className="imp-status">
          {imp.status === "writing" ? k.importWriting
            : imp.pages_total ? k.importReading.replace("{done}", nf.format(imp.pages_done)).replace("{total}", nf.format(imp.pages_total))
            : k.importStarting}
        </div>
        <div className="actions">
          <p className="hint grow">{k.importWait}</p>
          <button className="btn btn-secondary" onClick={close}>{k.cancel}</button>
        </div>
      </div>
    );
  }

  // Couldn't read the site
  if (imp.status === "failed") {
    return (
      <div className="card">
        <h2>{k.importTitle}</h2>
        <p className="hint" dir="ltr">{host(imp.url)}</p>
        <div className="alert alert-error">
          {imp.error === "unreachable" ? k.importUnreachable : imp.error === "empty" ? k.importEmpty : k.error}
        </div>
        <div className="actions">
          <span className="spacer" />
          <button className="btn btn-secondary" onClick={close}>{k.cancel}</button>
          <button className="btn" onClick={async () => { await api(`/knowledge/import/${imp.id}`, { method: "DELETE" }).catch(() => {}); setImp(null); setAsking(true); }}>
            {k.importTryAgain}
          </button>
        </div>
      </div>
    );
  }

  // Review
  return (
    <div className="card">
      <h2>{k.importReviewTitle}</h2>
      <p className="hint">
        {k.importReviewHint.replace("{site}", host(imp.url)).replace("{n}", nf.format(imp.pages_read))}
      </p>
      {items.map((it, n) => (
        <div key={n} className="sug">
          <input type="checkbox" checked={it.keep} aria-label={it.title} onChange={(e) => edit(n, { keep: e.target.checked })} />
          <div className="sug-main">
            {it.editing ? (
              <div className="sug-edit">
                <input dir="auto" maxLength={200} value={it.title} onChange={(e) => edit(n, { title: e.target.value })} />
                <textarea dir="auto" rows={6} value={it.body} onChange={(e) => edit(n, { body: e.target.value })} />
              </div>
            ) : (
              <>
                <div className="sug-title" dir="auto">
                  {it.title}
                  {it.exists && <span className="tag-info">{k.importExists.replace("{title}", it.title)}</span>}
                </div>
                <div className="sug-snip" dir="auto">{it.body.slice(0, 220)}{it.body.length > 220 ? "…" : ""}</div>
              </>
            )}
            <div className="sug-meta">
              <span>{nf.format(it.title.trim().length + it.body.trim().length)} {k.characters}</span>
              {it.source && <a href={it.source} target="_blank" rel="noreferrer" dir="ltr">{host(it.source)}</a>}
              <button type="button" className="link-btn" disabled={it.editing && (!it.title.trim() || !it.body.trim())}
                onClick={() => edit(n, { editing: !it.editing })}>
                {it.editing ? k.importDone : k.edit}
              </button>
            </div>
          </div>
        </div>
      ))}
      {error && <p className="error-text">{error}</p>}
      <div className="sug-foot">
        <div className={`grow${left < 0 ? " remaining-over" : ""}`}>
          {left >= 0
            ? k.importSize.replace("{size}", nf.format(size)).replace("{left}", nf.format(left))
            : k.importOver.replace("{size}", nf.format(size)).replace("{over}", nf.format(-left))}
        </div>
        <button className="btn btn-secondary" onClick={close}>{k.cancel}</button>
        <button className="btn" disabled={busy || kept.length === 0 || left < 0 || kept.some((i) => !i.title.trim() || !i.body.trim())}
          onClick={add}>
          {kept.length === 1 ? k.importAddOne : k.importAdd.replace("{n}", nf.format(kept.length))}
        </button>
      </div>
    </div>
  );
}
