"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

type Plan = {
  id: string;
  code: string;
  name: string;
  price_usd: number;
  billing_period: "one_time" | "monthly" | "trial";
  conversation_quota: number;
  max_channels: number;
  kb_char_limit: number;
  seats: number;
  show_branding: boolean;
};
type Custom = {
  id: string; status: "open" | "offered"; conversations: number; kb_chars: number; seats: number; notes: string | null;
  offer_price: number | null; offer_expires_at: string | null; expired: boolean;
};
type Data = {
  plans: Plan[];
  current: string | null;
  request: { plan_code: string; plan_name: string; created_at: string } | null;
  channels_used: number;
  custom: Custom | null;
  custom_defaults: { conversations: number; kb_chars: number; seats: number };
};

const ALL_CHANNELS = 4;
const POPULAR = "business";
const fill = (s: string, v: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

/** The plans a business can move to, and the Custom plan. Choosing a plan
    sends a request (the super-admin assigns it until payments are connected). */
export default function PlanPicker() {
  const { t, lang } = useI18n();
  const p = t.plan;
  const nf = new Intl.NumberFormat(lang);
  const router = useRouter();
  const [data, setData] = useState<Data | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [form, setForm] = useState<{ conversations: string; kb_chars: string; seats: string; notes: string } | null>(null);

  async function load() {
    try {
      setData(await api<Data>("/billing/plans"));
    } catch {
      setError(true);
    }
  }
  useEffect(() => { load(); }, []);

  async function act(key: string, fn: () => Promise<unknown>, refresh = false) {
    setBusy(key);
    setError(false);
    try {
      await fn();
      await load();
      if (refresh) router.refresh();     // the plan name and limits elsewhere in the panel
    } catch {
      setError(true);
    } finally {
      setBusy(null);
    }
  }

  const choose = (code: string) => act(code, async () => {
    const r = await api<{ status: string; url?: string }>("/billing/checkout", { method: "POST", body: JSON.stringify({ plan_code: code }) });
    if (r.status === "redirect" && r.url) window.location.href = r.url;    // a payment provider's checkout page
  });

  function openForm() {
    if (!data) return;
    const d = data.custom_defaults;
    setForm({ conversations: String(d.conversations), kb_chars: String(d.kb_chars), seats: String(d.seats), notes: "" });
  }

  const sendCustom = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    act("custom", async () => {
      await api("/billing/custom", { method: "POST", body: JSON.stringify({
        conversations: Number(form.conversations), kb_chars: Number(form.kb_chars), seats: Number(form.seats), notes: form.notes,
      }) });
      setForm(null);
    });
  };

  const accept = (id: string) => act("accept", async () => {
    try {
      await api(`/billing/custom/${id}/accept`, { method: "POST" });
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 410)) throw e;   // expired: shown after reloading
    }
  }, true);

  if (!data) return error ? <p className="error-text">{p.error}</p> : null;
  const c = data.custom;
  const formValid = !!form && [form.conversations, form.kb_chars, form.seats].every((v) => /^\d+$/.test(v) && Number(v) > 0)
    && Number(form.kb_chars) >= 1000;

  return (
    <>
      {c?.status === "offered" && (
        <div className="card offer-card">
          <div className="row-between">
            <div className="grow">
              <h2 className="offer-title">{p.offerTitle}</h2>
              <p className="hint">
                {c.expired ? p.offerExpired
                  : fill(p.offerValid, { date: new Date(c.offer_expires_at!).toLocaleDateString(lang, { dateStyle: "long" }) })}
              </p>
            </div>
            <div className="offer-price" dir="ltr">${nf.format(c.offer_price ?? 0)} <span className="hint">{p.perMonthShort}</span></div>
          </div>
          <ul className="offer-terms">
            <li>{fill(p.aiConvMonth, { n: nf.format(c.conversations) })}</li>
            <li>{p.humanUnlimited}</li>
            <li>{fill(p.allChannels, { n: ALL_CHANNELS })}</li>
            <li>{fill(p.knowledge, { n: nf.format(c.kb_chars) })}</li>
            <li>{fill(c.seats === 1 ? p.oneSeat : p.nSeats, { n: c.seats })}</li>
            <li>{p.noBranding}</li>
          </ul>
          <div className="actions">
            <span className="spacer" />
            {c.expired ? (
              <button className="btn" disabled={!!busy} onClick={openForm}>{p.customAsk}</button>
            ) : (
              <>
                <button className="btn btn-secondary" disabled={!!busy}
                  onClick={() => act("decline", () => api("/billing/custom", { method: "DELETE" }))}>{p.decline}</button>
                <button className="btn" disabled={!!busy} onClick={() => accept(c.id)}>{busy === "accept" ? "…" : p.accept}</button>
              </>
            )}
          </div>
        </div>
      )}

      <h2 className="section-title">{p.choosePlan}</h2>
      {data.request && (
        <div className="alert alert-ok plan-request">
          {fill(p.requested, { plan: data.request.plan_name })}{" "}
          <button className="link-btn" disabled={busy === "cancel"}
            onClick={() => act("cancel", () => api("/billing/request", { method: "DELETE" }))}>{p.cancelRequest}</button>
        </div>
      )}
      <div className="plan-grid">
        {data.plans.map((x) => {
          const current = x.code === data.current;
          const requested = data.request?.plan_code === x.code;
          const popular = x.code === POPULAR;
          const extra = data.channels_used - x.max_channels;
          return (
            <div key={x.id} className={`card plan-card${popular ? " plan-popular" : ""}${current ? " plan-current" : ""}`}>
              {popular && <span className="plan-badge">{p.popular}</span>}
              <div className="plan-head">
                <h3>{x.name}</h3>
                {current && <span className="pill pill-on">{p.current}</span>}
              </div>
              <div className="plan-price">
                <b dir="ltr">${nf.format(x.price_usd)}</b> <span className="hint">{p.perMonthShort}</span>
              </div>
              <ul className="plan-features">
                <li>{fill(p.aiConvMonth, { n: nf.format(x.conversation_quota) })}</li>
                <li>{p.humanUnlimited}</li>
                <li>{fill(x.max_channels >= ALL_CHANNELS ? p.allChannels : p.anyChannels, { n: x.max_channels })}</li>
                <li>{fill(p.knowledge, { n: nf.format(x.kb_char_limit) })}</li>
                <li>{fill(x.seats === 1 ? p.oneSeat : p.nSeats, { n: x.seats })}</li>
                {x.show_branding ? <li className="off">{p.branding}</li> : <li>{p.noBranding}</li>}
              </ul>
              {!current && extra > 0 && !requested && (
                <div className="plan-note">
                  {fill(p.channelsNote, { plan: x.name, limit: x.max_channels, used: data.channels_used, extra })}
                </div>
              )}
              {!current && (
                requested ? (
                  <div className="plan-requested">{p.requestedShort}</div>
                ) : (
                  <button className={`btn${popular ? "" : " btn-secondary"}`} disabled={!!busy || extra > 0} onClick={() => choose(x.code)}>
                    {busy === x.code ? "…" : fill(p.chooseName, { plan: x.name })}
                  </button>
                )
              )}
            </div>
          );
        })}
      </div>

      {form ? (
        <form className="card custom-form" onSubmit={sendCustom}>
          <h2>{p.customFormTitle}</h2>
          <p className="hint">{p.customFormHint}</p>
          <div className="custom-grid">
            {([["conversations", p.customConv], ["kb_chars", p.customKb], ["seats", p.customSeats]] as const).map(([k, label]) => (
              <label key={k}>
                {label}
                <input dir="ltr" inputMode="numeric" value={form[k]}
                  onChange={(e) => setForm({ ...form, [k]: e.target.value.replace(/[^\d]/g, "") })} />
              </label>
            ))}
          </div>
          <p className="hint">{p.customChannels}</p>
          <label className="custom-notes">
            {p.customNotes}
            <textarea dir="auto" rows={3} maxLength={2000} placeholder={p.customNotesPh} value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </label>
          <div className="actions">
            <span className="spacer" />
            <button type="button" className="btn btn-secondary" onClick={() => setForm(null)}>{p.cancel}</button>
            <button className="btn" disabled={!!busy || !formValid}>{busy === "custom" ? "…" : p.customSend}</button>
          </div>
        </form>
      ) : c?.status === "open" ? (
        <div className="alert alert-ok custom-sent">
          {fill(p.customSent, { conv: nf.format(c.conversations), kb: nf.format(c.kb_chars), seats: c.seats })}{" "}
          <button className="link-btn" disabled={!!busy}
            onClick={() => act("withdraw", () => api("/billing/custom", { method: "DELETE" }))}>{p.cancelRequest}</button>
        </div>
      ) : c?.status !== "offered" && (
        <div className="card custom-card">
          <div className="grow">
            <h3>{p.customTitle}</h3>
            <p className="hint">{p.customHint}</p>
          </div>
          <button className="btn btn-secondary" onClick={openForm}>{p.customAsk}</button>
        </div>
      )}
      {error && <p className="error-text">{p.error}</p>}
    </>
  );
}
