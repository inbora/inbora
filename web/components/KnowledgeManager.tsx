"use client";

import { useMemo, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

export type Article = {
  id: string;
  title: string;
  body: string;
  enabled: boolean;
  char_count: number;
  sort_order: number;
};
type Listing = { articles: Article[]; used: number; limit: number };
type Draft = { id: string | null; title: string; body: string; enabled: boolean };

const TEMPLATE_KEYS = ["shipping", "returns", "payment", "contact", "hours"] as const;
const hasBrackets = (s: string) => /\[[^\]\n]{1,60}\]/.test(s);

export default function KnowledgeManager({ initial }: { initial: Listing }) {
  const { t, lang } = useI18n();
  const k = t.knowledge;
  const nf = useMemo(() => new Intl.NumberFormat(lang), [lang]);
  const [data, setData] = useState<Listing>(initial);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);
  const [picked, setPicked] = useState<string[]>([...TEMPLATE_KEYS]);
  const [tplLang, setTplLang] = useState<string>(lang);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function reload() {
    setData(await api<Listing>("/knowledge"));
  }

  function errorText(e: unknown) {
    if (e instanceof ApiError && e.status === 422) {
      const d = e.detail as { code?: string; limit?: number; used?: number } | null;
      if (d?.code === "kb_limit") {
        return k.overLimit.replace("{limit}", nf.format(d.limit ?? 0)).replace("{used}", nf.format(d.used ?? 0));
      }
    }
    return k.error;
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const save = () =>
    run(async () => {
      if (!draft) return;
      const body = JSON.stringify({ title: draft.title, body: draft.body, enabled: draft.enabled });
      if (draft.id) await api(`/knowledge/${draft.id}`, { method: "PUT", body });
      else await api("/knowledge", { method: "POST", body });
      setDraft(null);
      await reload();
    });

  const toggle = (a: Article) =>
    run(async () => {
      await api(`/knowledge/${a.id}`, { method: "PUT", body: JSON.stringify({ enabled: !a.enabled }) });
      await reload();
    });

  const remove = (a: Article) => {
    if (!confirm(k.confirmDelete)) return;
    run(async () => {
      await api(`/knowledge/${a.id}`, { method: "DELETE" });
      if (draft?.id === a.id) setDraft(null);
      await reload();
    });
  };

  const addTemplates = () =>
    run(async () => {
      await api("/knowledge/templates", { method: "POST", body: JSON.stringify({ keys: picked, language: tplLang }) });
      setShowTemplates(false);
      await reload();
    });

  // Live counter for the editor.
  const draftSize = draft ? draft.title.trim().length + draft.body.trim().length : 0;
  const othersUsed = data.articles
    .filter((a) => a.enabled && a.id !== draft?.id)
    .reduce((n, a) => n + a.char_count, 0);
  const after = othersUsed + (draft?.enabled ? draftSize : 0);
  const draftOver = !!draft?.enabled && after > data.limit;

  const pct = data.limit ? Math.min(100, Math.round((data.used / data.limit) * 100)) : 0;

  return (
    <>
      <div className="card">
        <div className="row-between">
          <div className="grow">
            <div className="stat-label">{k.usage}</div>
            <div className="meter"><span style={{ width: `${pct}%` }} className={pct >= 100 ? "meter-full" : ""} /></div>
            <div className="hint">
              {nf.format(data.used)} / {nf.format(data.limit)} {k.characters}
            </div>
          </div>
          <div className="actions">
            <button className="btn btn-secondary" disabled={busy}
              onClick={() => { setShowTemplates((v) => !v); setDraft(null); }}>
              {k.addTemplates}
            </button>
            <button className="btn" disabled={busy}
              onClick={() => { setDraft({ id: null, title: "", body: "", enabled: true }); setShowTemplates(false); }}>
              {k.newArticle}
            </button>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {showTemplates && (
        <div className="card">
          <h2>{k.templatesTitle}</h2>
          <p className="hint">{k.templatesHint}</p>
          <div className="checks">
            {TEMPLATE_KEYS.map((key) => (
              <label key={key} className="check">
                <input type="checkbox" checked={picked.includes(key)}
                  onChange={(e) => setPicked(e.target.checked ? [...picked, key] : picked.filter((x) => x !== key))} />
                {k.templateNames[key]}
              </label>
            ))}
          </div>
          <div className="actions">
            <label className="inline-field">
              {k.templateLanguage}
              <select className="lang" value={tplLang} onChange={(e) => setTplLang(e.target.value)}>
                <option value="en">English</option>
                <option value="he">עברית</option>
                <option value="ar">العربية</option>
              </select>
            </label>
            <button className="btn btn-secondary" onClick={() => setShowTemplates(false)}>{k.cancel}</button>
            <button className="btn" disabled={busy || picked.length === 0} onClick={addTemplates}>{k.add}</button>
          </div>
        </div>
      )}

      {draft && (
        <div className="card editor">
          <div className="field">
            <label htmlFor="kb-title">{k.articleTitle}</label>
            <input id="kb-title" dir="auto" maxLength={200} value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="kb-body">{k.articleBody}</label>
            <textarea id="kb-body" dir="auto" rows={12} value={draft.body}
              onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
            <span className="hint">{k.bodyHint}</span>
          </div>
          <label className="check">
            <input type="checkbox" checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} />
            {k.enabled}
          </label>
          <div className={`hint counter${draftOver ? " counter-over" : ""}`}>
            {k.thisArticle}: {nf.format(draftSize)} · {k.afterSave}: {nf.format(after)} / {nf.format(data.limit)} {k.characters}
          </div>
          {draftOver && (
            <div className="alert alert-warn">
              {k.overLimit.replace("{limit}", nf.format(data.limit)).replace("{used}", nf.format(othersUsed))}
            </div>
          )}
          <div className="actions">
            <button className="btn btn-secondary" onClick={() => { setDraft(null); setError(""); }}>{k.cancel}</button>
            <button className="btn" disabled={busy || !draft.title.trim() || draftOver} onClick={save}>{k.save}</button>
          </div>
        </div>
      )}

      {data.articles.length === 0 && !draft && !showTemplates && (
        <div className="card empty"><p>{k.empty}</p></div>
      )}

      <div className="article-list">
        {data.articles.map((a) => (
          <div key={a.id} className={`card article${a.enabled ? "" : " article-off"}`}>
            <div className="article-main">
              <div className="article-title" dir="auto">{a.title}</div>
              <div className="article-snippet" dir="auto">{a.body.slice(0, 160)}{a.body.length > 160 ? "…" : ""}</div>
              <div className="article-meta">
                <span>{nf.format(a.char_count)} {k.characters}</span>
                {hasBrackets(a.body) && <span className="tag-warn">{k.fillBrackets}</span>}
              </div>
            </div>
            <div className="article-actions">
              <button className={`switch${a.enabled ? " switch-on" : ""}`} role="switch" aria-checked={a.enabled}
                disabled={busy} onClick={() => toggle(a)} title={a.enabled ? k.on : k.off}>
                <span />
              </button>
              <button className="link-btn" disabled={busy}
                onClick={() => { setDraft({ id: a.id, title: a.title, body: a.body, enabled: a.enabled }); setShowTemplates(false); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                {k.edit}
              </button>
              <button className="link-btn link-danger" disabled={busy} onClick={() => remove(a)}>{k.delete}</button>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
