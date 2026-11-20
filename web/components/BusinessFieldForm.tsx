"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

/** The business name or ID (owners and admins). */
export default function BusinessFieldForm({ field, initial }: { field: "name" | "slug"; initial: string }) {
  const { t } = useI18n();
  const s = t.settings;
  const router = useRouter();
  const [value, setValue] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setStatus("");
    try {
      const r = await api<{ name: string; slug: string }>("/me/business", { method: "PUT", body: JSON.stringify({ [field]: value }) });
      setValue(r[field]);
      setSaved(r[field]);
      setStatus(s.saved);
      router.refresh();
    } catch (err) {
      setStatus(err instanceof ApiError && err.status === 409 ? s.idTaken
        : err instanceof ApiError && err.status === 422 && field === "slug" ? s.idInvalid : s.error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="name-form" onSubmit={save}>
      <input dir={field === "slug" ? "ltr" : "auto"} maxLength={field === "slug" ? 40 : 80} value={value}
        onChange={(e) => { setValue(field === "slug" ? e.target.value.toLowerCase() : e.target.value); setStatus(""); }} />
      <button className="btn btn-sm" disabled={busy || !value.trim() || value.trim() === saved}>{s.save}</button>
      {status && <span className={status === s.saved ? "saved" : "error-text"}>{status}</span>}
    </form>
  );
}
