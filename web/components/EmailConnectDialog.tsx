"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

type Discovery = {
  email: string;
  route: "google_oauth" | "microsoft_oauth" | "imap" | "unsupported" | "hosted";
  provider: string | null;
  password_kind: "app_password" | "password" | "oauth" | null;
  help_url: string | null;
  enable_imap_url: string | null;
  needs_imap_on: boolean;
  unsupported_reason: string | null;
  suggested_email: string | null;
};

const fill = (s: string, v: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

/** Connect Email in our own window: the address first; Gmail and Outlook go
    straight to Google's / Microsoft's sign-in, any other mailbox connects here
    with its app password. No Zernio page. */
export default function EmailConnectDialog({ initialEmail, onClose, onConnected }: {
  initialEmail?: string | null;
  onClose: () => void;
  onConnected: () => void;
}) {
  const { t } = useI18n();
  const e = t.channels.emailConnect;
  const [email, setEmail] = useState(initialEmail ?? "");
  const [found, setFound] = useState<Discovery | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState<"" | "check" | "redirect" | "connect">("");
  const [error, setError] = useState("");

  function apiError(err: unknown) {
    const code = err instanceof ApiError ? (err.detail as { code?: string } | null)?.code : null;
    if (code === "bad_email") return e.badEmail;
    if (code === "wrong_password") return e.wrongPassword;
    if (code === "connect_failed") return e.connectFailed;
    if (code === "channel_limit") return t.channels.error;
    return e.error;
  }

  async function check(address = email) {
    setBusy("check");
    setError("");
    try {
      const d = await api<Discovery>("/channels/email/discover", { method: "POST", body: JSON.stringify({ email: address }) });
      setEmail(d.email);
      if (d.route === "google_oauth" || d.route === "microsoft_oauth" || d.route === "hosted") {
        // hosted = a mailbox type we can't tell: Zernio's own page, address filled in.
        setBusy("redirect");
        const r = await api<{ url: string }>("/channels/email/connect", {
          method: "POST", body: JSON.stringify({ email: d.email, route: d.route === "hosted" ? null : d.route }),
        });
        window.location.href = r.url;           // Google's / Microsoft's own sign-in
        return;
      }
      setFound(d);
    } catch (err) {
      setError(apiError(err));
    }
    setBusy("");
  }

  async function connect() {
    if (!found) return;
    setBusy("connect");
    setError("");
    try {
      await api("/channels/email/imap", { method: "POST", body: JSON.stringify({ email: found.email, password }) });
      onConnected();
    } catch (err) {
      setError(apiError(err));
      setBusy("");
    }
  }

  const unsupported = found?.route === "unsupported";
  const passwordStep = found?.route === "imap";
  const appPassword = found?.password_kind !== "password";
  const reasons = e.unsupported as Record<string, string>;

  return (
    <div className="modal-bg" onClick={() => !busy && onClose()}>
      <div className="modal email-connect" role="dialog" aria-modal="true" onClick={(ev) => ev.stopPropagation()}>
        {!passwordStep ? (
          <form onSubmit={(ev) => { ev.preventDefault(); if (email.trim()) check(); }}>
            <h3>{e.title}</h3>
            <p>{e.intro}</p>
            <label className="ec-label" htmlFor="ec-email">{e.address}</label>
            <input id="ec-email" type="email" dir="ltr" autoFocus autoComplete="email" value={email} disabled={!!busy}
              placeholder="support@yourshop.com" onChange={(ev) => { setEmail(ev.target.value); setFound(null); }} />
            {unsupported && (
              <div className="alert alert-warn ec-note">
                {reasons[found.unsupported_reason ?? ""] ?? reasons.other}
                {found.suggested_email && (
                  <> <button type="button" className="link-btn" onClick={() => check(found.suggested_email!)}>
                    {fill(e.useSuggested, { email: found.suggested_email })}
                  </button></>
                )}
              </div>
            )}
            {error && <p className="error-text">{error}</p>}
            <div className="actions">
              <button type="button" className="btn btn-secondary" disabled={!!busy} onClick={onClose}>{e.cancel}</button>
              <button type="submit" className="btn" disabled={!!busy || !email.trim()}>
                {busy === "check" ? e.checking : busy === "redirect" ? e.opening : e.continue}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={(ev) => { ev.preventDefault(); if (password) connect(); }}>
            <h3 dir="auto">{fill(e.connectTitle, { email: found.email })}</h3>
            <p>{appPassword ? e.appPasswordIntro : e.passwordIntro}</p>
            {found.needs_imap_on && (
              <p className="ec-imap">
                {fill(e.imapFirst, { provider: found.provider ?? e.yourProvider })}
                {found.enable_imap_url && <> <a href={found.enable_imap_url} target="_blank" rel="noreferrer">{e.openSettings} ↗</a></>}
              </p>
            )}
            {appPassword && (
              <ol className="ec-steps">
                <li>{fill(e.step1, { provider: found.provider ?? e.yourProvider })}</li>
                <li>{e.step2}</li>
                <li>{e.step3}</li>
              </ol>
            )}
            {appPassword && found.help_url && (
              <p><a href={found.help_url} target="_blank" rel="noreferrer">{e.howTo} ↗</a></p>
            )}
            <label className="ec-label" htmlFor="ec-pass">{appPassword ? e.appPassword : e.password}</label>
            <input id="ec-pass" type="password" dir="ltr" autoFocus autoComplete="off" value={password} disabled={!!busy}
              onChange={(ev) => setPassword(ev.target.value)} />
            {error && <p className="error-text">{error}</p>}
            <div className="actions">
              <button type="button" className="btn btn-secondary" disabled={!!busy}
                onClick={() => { setFound(null); setPassword(""); setError(""); }}>{e.back}</button>
              <button type="submit" className="btn" disabled={!!busy || !password}>
                {busy === "connect" ? e.connecting : e.connect}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
