"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useI18n } from "@/lib/i18n/client";
import { siteUrl } from "@/lib/site";
import { createClient } from "@/lib/supabase/client";

export default function SignupPage() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const [business, setBusiness] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const { data, error } = await createClient().auth.signUp({
      email,
      password,
      options: {
        // Read by the database signup trigger to create the business.
        data: { business_name: business.trim(), language: lang },
        emailRedirectTo: `${siteUrl()}/auth/callback?next=/inbox`,
      },
    });
    setBusy(false);
    if (error) {
      setError(error.message || t.auth.genericError);
      return;
    }
    if (data.session) {
      // Email confirmation is off: already logged in.
      router.replace("/inbox");
      router.refresh();
      return;
    }
    setDone(true);
  }

  if (done) {
    return (
      <div>
        <h1>{t.auth.signupTitle}</h1>
        <div className="alert alert-ok">{t.auth.checkEmail}</div>
        <div className="auth-links">
          <Link href="/login">{t.auth.backToLogin}</Link>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={submit}>
      <h1>{t.auth.signupTitle}</h1>
      {error && <div className="alert alert-error">{error}</div>}
      <div className="field">
        <label htmlFor="business">{t.auth.businessName}</label>
        <input id="business" required maxLength={80}
          value={business} onChange={(e) => setBusiness(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="email">{t.auth.email}</label>
        <input id="email" type="email" dir="ltr" autoComplete="email" required
          value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="password">{t.auth.password}</label>
        <input id="password" type="password" dir="ltr" autoComplete="new-password" required minLength={8}
          value={password} onChange={(e) => setPassword(e.target.value)} />
        <span className="hint">{t.auth.passwordHint}</span>
      </div>
      <button className="btn" disabled={busy}>{t.auth.signupButton}</button>
      <div className="auth-links">
        <span>
          {t.auth.haveAccount} <Link href="/login">{t.auth.loginLink}</Link>
        </span>
      </div>
    </form>
  );
}
