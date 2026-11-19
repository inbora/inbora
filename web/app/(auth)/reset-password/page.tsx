"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useI18n } from "@/lib/i18n/client";
import { createClient } from "@/lib/supabase/client";

// Reached from the reset email: the link logs the user in, then they set a
// new password here.
export default function ResetPasswordPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const { error } = await createClient().auth.updateUser({ password });
    setBusy(false);
    if (error) {
      setError(error.message || t.auth.genericError);
      return;
    }
    setSaved(true);
    setTimeout(() => router.replace("/inbox"), 1200);
  }

  return (
    <form onSubmit={submit}>
      <h1>{t.auth.setPasswordTitle}</h1>
      {error && <div className="alert alert-error">{error}</div>}
      {saved && <div className="alert alert-ok">{t.auth.passwordSaved}</div>}
      <div className="field">
        <label htmlFor="password">{t.auth.newPassword}</label>
        <input id="password" type="password" dir="ltr" autoComplete="new-password" required minLength={8}
          value={password} onChange={(e) => setPassword(e.target.value)} />
        <span className="hint">{t.auth.passwordHint}</span>
      </div>
      <button className="btn" disabled={busy || saved}>{t.auth.setPasswordButton}</button>
    </form>
  );
}
