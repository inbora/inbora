"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useI18n } from "@/lib/i18n/client";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const { error } = await createClient().auth.signInWithPassword({ email, password });
    if (error) {
      setError(error.message || t.auth.genericError);
      setBusy(false);
      return;
    }
    router.replace("/inbox");
    router.refresh();
  }

  return (
    <form onSubmit={submit}>
      <h1>{t.auth.loginTitle}</h1>
      {error && <div className="alert alert-error">{error}</div>}
      <div className="field">
        <label htmlFor="email">{t.auth.email}</label>
        <input id="email" type="email" dir="ltr" autoComplete="email" required
          value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="password">{t.auth.password}</label>
        <input id="password" type="password" dir="ltr" autoComplete="current-password" required
          value={password} onChange={(e) => setPassword(e.target.value)} />
      </div>
      <button className="btn" disabled={busy}>{t.auth.loginButton}</button>
      <div className="auth-links">
        <Link href="/forgot-password">{t.auth.forgot}</Link>
        <span>
          {t.auth.noAccount} <Link href="/signup">{t.auth.signupLink}</Link>
        </span>
      </div>
    </form>
  );
}
