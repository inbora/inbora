"use client";

import Link from "next/link";
import { useState } from "react";
import { useI18n } from "@/lib/i18n/client";
import { siteUrl } from "@/lib/site";
import { createClient } from "@/lib/supabase/client";

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const { error } = await createClient().auth.resetPasswordForEmail(email, {
      redirectTo: `${siteUrl()}/auth/callback?next=/reset-password`,
    });
    setBusy(false);
    if (error) setError(error.message || t.auth.genericError);
    else setSent(true);
  }

  return (
    <form onSubmit={submit}>
      <h1>{t.auth.resetTitle}</h1>
      {error && <div className="alert alert-error">{error}</div>}
      {sent ? (
        <div className="alert alert-ok">{t.auth.resetSent}</div>
      ) : (
        <>
          <div className="field">
            <label htmlFor="email">{t.auth.email}</label>
            <input id="email" type="email" dir="ltr" autoComplete="email" required
              value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <button className="btn" disabled={busy}>{t.auth.resetButton}</button>
        </>
      )}
      <div className="auth-links">
        <Link href="/login">{t.auth.backToLogin}</Link>
      </div>
    </form>
  );
}
