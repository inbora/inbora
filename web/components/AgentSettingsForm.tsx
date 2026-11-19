"use client";

import { useState } from "react";
import { api } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

export type AgentSettings = {
  instructions: string;
  tone: "friendly" | "professional" | "casual" | "formal";
  default_language: "en" | "he" | "ar";
  greeting: string;
  escalation_message: string;
};

const TONES = ["friendly", "professional", "casual", "formal"] as const;

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
            onChange={(e) => set("default_language", e.target.value as AgentSettings["default_language"])}>
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
        <label htmlFor="ag-esc">{s.escalation}</label>
        <textarea id="ag-esc" dir="auto" rows={2} maxLength={1000} value={form.escalation_message}
          onChange={(e) => set("escalation_message", e.target.value)} />
        <span className="hint">{s.escalationHint}</span>
      </div>
      <div className="actions">
        {status === "saved" && <span className="saved">{s.saved}</span>}
        {status === "error" && <span className="error-text">{s.error}</span>}
        <button className="btn" disabled={busy}>{s.save}</button>
      </div>
    </form>
  );
}
