"use client";

import { useState } from "react";
import { api } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

/** The user's own name: shown on their inbox replies and used to sign AI drafts. */
export default function ProfileNameForm({ initial }: { initial: string }) {
  const { t } = useI18n();
  const s = t.settings;
  const [name, setName] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"" | "saved" | "error">("");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setStatus("");
    try {
      const r = await api<{ full_name: string }>("/me/profile", { method: "PUT", body: JSON.stringify({ full_name: name }) });
      setName(r.full_name);
      setSaved(r.full_name);
      setStatus("saved");
    } catch {
      setStatus("error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="name-form" onSubmit={save}>
      <input dir={name ? "auto" : undefined} maxLength={80} placeholder={s.yourNamePlaceholder} value={name}
        onChange={(e) => { setName(e.target.value); setStatus(""); }} />
      <button className="btn btn-sm" disabled={busy || name.trim() === saved}>{s.save}</button>
      {status === "saved" && <span className="saved">{s.saved}</span>}
      {status === "error" && <span className="error-text">{s.error}</span>}
    </form>
  );
}
