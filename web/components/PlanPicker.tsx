"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

type Plan = {
  id: string;
  code: string;
  name: string;
  price_usd: number;
  billing_period: "one_time" | "monthly";
  conversation_quota: number;
  max_channels: number;
  kb_char_limit: number;
  seats: number;
  show_branding: boolean;
};
type Data = { plans: Plan[]; current: string | null; request: { plan_code: string; plan_name: string; created_at: string } | null };

const fill = (s: string, v: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

/** The plans a business can move to. Choosing one sends a request (the
    super-admin assigns it until payments are connected). */
export default function PlanPicker() {
  const { t, lang } = useI18n();
  const p = t.plan;
  const nf = new Intl.NumberFormat(lang);
  const [data, setData] = useState<Data | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState(false);

  async function load() {
    try {
      setData(await api<Data>("/billing/plans"));
    } catch {
      setError(true);
    }
  }
  useEffect(() => { load(); }, []);

  async function choose(code: string) {
    setBusy(code);
    setError(false);
    try {
      const r = await api<{ status: string; url?: string }>("/billing/checkout", { method: "POST", body: JSON.stringify({ plan_code: code }) });
      if (r.status === "redirect" && r.url) {
        window.location.href = r.url;       // a payment provider's checkout page
        return;
      }
      await load();
    } catch {
      setError(true);
    } finally {
      setBusy(null);
    }
  }

  async function cancelRequest() {
    setBusy("cancel");
    try {
      await api("/billing/request", { method: "DELETE" });
      await load();
    } finally {
      setBusy(null);
    }
  }

  if (!data) return error ? <p className="error-text">{p.error}</p> : null;

  return (
    <>
      <h2 className="section-title">{p.plans}</h2>
      {data.request && (
        <div className="alert alert-ok plan-request">
          {fill(p.requested, { plan: data.request.plan_name })}{" "}
          <button className="link-btn" disabled={busy === "cancel"} onClick={cancelRequest}>{p.cancelRequest}</button>
        </div>
      )}
      <div className="plan-grid">
        {data.plans.map((x) => {
          const current = x.code === data.current;
          const requested = data.request?.plan_code === x.code;
          const monthly = x.billing_period === "monthly";
          return (
            <div key={x.id} className={`card plan-card${current ? " plan-current" : ""}`}>
              <div className="plan-head">
                <h3>{x.name}</h3>
                {current && <span className="pill pill-on">{p.current}</span>}
              </div>
              <div className="plan-price">
                <b dir="ltr">${nf.format(x.price_usd)}</b>{" "}
                {monthly && <span className="hint">{p.perMonthShort}</span>}
              </div>
              <ul className="plan-features">
                <li>{fill(monthly ? p.convMonth : p.convTotal, { n: nf.format(x.conversation_quota) })}</li>
                <li>{fill(x.max_channels === 1 ? p.oneChannel : p.nChannels, { n: x.max_channels })}</li>
                <li>{fill(p.knowledge, { n: nf.format(x.kb_char_limit) })}</li>
                <li>{fill(x.seats === 1 ? p.oneSeat : p.nSeats, { n: x.seats })}</li>
                {!x.show_branding && <li>{p.noBranding}</li>}
              </ul>
              {!current && (
                requested ? (
                  <div className="plan-requested">{p.requestedShort}</div>
                ) : (
                  <button className={`btn ${x.price_usd > 0 ? "" : "btn-secondary"}`} disabled={!!busy} onClick={() => choose(x.code)}>
                    {busy === x.code ? "…" : p.choose}
                  </button>
                )
              )}
            </div>
          );
        })}
      </div>
      {error && <p className="error-text">{p.error}</p>}
    </>
  );
}
