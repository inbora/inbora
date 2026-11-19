"use client";

import { useState } from "react";
import { api } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

type Lang = "en" | "he" | "ar";
type Texts = { greeting: string };

export type AgentSettings = {
  instructions: string;
  tone: "friendly" | "professional" | "casual" | "formal";
  default_language: Lang;
  greeting: string;
  collect_contact: "email" | "phone" | "either" | "none";
  defaults: Record<Lang, Texts>;
};

const TONES = ["friendly", "professional", "casual", "formal"] as const;
const COLLECT = ["email", "phone", "either", "none"] as const;

export default function AgentSettingsForm({ initial }: { initial: AgentSettings }) {
  const { t, lang } = useI18n();
  const s = t.agentSettings;
  const [form, setForm] = useState<AgentSettings>(initial);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"" | "saved" | "error">("");
  const set = <K extends keyof AgentSettings>(key: K, v: AgentSettings[K]) => {
    setForm({ ...form, [key]: v });
    setStatus("");
  };

  // Changing the language swaps the greeting to the new language's default,
  // but only if it's still exactly the old default (or empty). A greeting the
  // business wrote itself is kept.
  function changeLanguage(next: Lang) {
    const before = form.defaults[form.default_language];
    const after = form.defaults[next];
    const swap = (field: keyof Texts) =>
      !form[field].trim() || form[field].trim() === before[field] ? after[field] : form[field];
    setForm({ ...form, default_language: next, greeting: swap("greeting") });
    setStatus("");
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      setForm(await api<AgentSettings>("/agent/settings", { method: "PUT", body: JSON.stringify(form) }));
      setStatus("saved");
    } catch {
      setStatus("error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={save}>
      <h2>{s.title}</h2>
      <div className="field">
        <label htmlFor="ag-instr">{s.instructions}</label>
        <textarea id="ag-instr" dir="auto" rows={6} maxLength={5000} placeholder={s.instructionsPlaceholder}
          value={form.instructions} onChange={(e) => set("instructions", e.target.value)} />
        <span className="hint">{s.instructionsHint} · {new Intl.NumberFormat(lang).format(form.instructions.length)} / 5,000</span>
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="ag-tone">{s.tone}</label>
          <select id="ag-tone" value={form.tone} onChange={(e) => set("tone", e.target.value as AgentSettings["tone"])}>
            {TONES.map((x) => <option key={x} value={x}>{s.tones[x]}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="ag-lang">{s.language}</label>
          <select id="ag-lang" value={form.default_language}
            onChange={(e) => changeLanguage(e.target.value as Lang)}>
            <option value="en">English</option>
            <option value="he">עברית</option>
            <option value="ar">العربية</option>
          </select>
          <span className="hint">{s.languageHint}</span>
        </div>
      </div>
      <div className="field">
        <label htmlFor="ag-greet">{s.greeting}</label>
        <input id="ag-greet" dir="auto" maxLength={500} value={form.greeting}
          onChange={(e) => set("greeting", e.target.value)} />
        <span className="hint">{s.greetingHint}</span>
      </div>
      <div className="field">
        <label htmlFor="ag-collect">{s.collect}</label>
        <select id="ag-collect" value={form.collect_contact ?? "email"}
          onChange={(e) => set("collect_contact", e.target.value as AgentSettings["collect_contact"])}>
          {COLLECT.map((x) => <option key={x} value={x}>{s.collectOptions[x]}</option>)}
        </select>
        <span className="hint">{s.collectHint}</span>
      </div>
      <div className="actions">
        {status === "saved" && <span className="saved">{s.saved}</span>}
        {status === "error" && <span className="error-text">{s.error}</span>}
        <button className="btn" disabled={busy}>{s.save}</button>
      </div>
    </form>
  );
}
