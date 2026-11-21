"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

export type Plan = {
  id: string; code: string; name: string; price_usd: number; billing_period: "one_time" | "monthly" | "trial"; trial_days?: number | null;
  conversation_quota: number; max_channels: number; kb_char_limit: number; seats: number;
  show_branding: boolean; is_public: boolean; is_signup_default: boolean; active: boolean;
};
export type Tenant = {
  id: string; name: string; status: "active" | "suspended"; created_at: string; plan: string | null; plan_id: string | null;
  used: number; quota: number; bonus: number; channels: string[]; broken: string[]; members: number;
};
export type CustomRequest = { id: string; tenant_id: string; tenant: string | null; current: string | null; status: "open" | "offered";
  conversations: number; kb_chars: number; seats: number; notes: string | null; offer_price: number | null;
  offer_expires_at: string | null; expired: boolean; created_at: string };
export type PlanRequest = { id: string; tenant_id: string; tenant: string; plan_id: string; plan: string; current: string | null; created_at: string };
type ErrorRow = { id: number; kind: string; where: string; message: string; detail: string | null; count: number;
  first_at: string; last_at: string; business: string | null };
type Deletion = { id: string; code: string; name: string | null; contact: string; business: string | null; details: string | null;
  status: "open" | "done" | "dismissed"; deleted_count: number | null; created_at: string;
  matches: { business: string | null; name: string | null; handle: string | null }[] };
type Tab = "businesses" | "plans" | "errors" | "deletion";

const fill = (s: string, v: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

/** The Super-admin page: businesses (and plan requests), plans, errors and
    data-deletion requests, as tabs. */
export default function AdminConsole({ plans, tenants, requests, custom, counts, initialTab }: {
  plans: Plan[]; tenants: Tenant[]; requests: PlanRequest[]; custom: CustomRequest[]; counts: { errors: number; deletions: number };
  initialTab: Tab;
}) {
  const { t } = useI18n();
  const a = t.admin;
  const [tab, setTab] = useState<Tab>(initialTab);

  function go(next: Tab) {
    setTab(next);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    window.history.replaceState(null, "", url.toString());
  }

  const tabs: [Tab, string, number][] = [
    ["businesses", a.tenants, requests.length + custom.filter((c) => c.status === "open").length],
    ["plans", a.plans, 0],
    ["errors", a.errors, counts.errors],
    ["deletion", a.deletion, counts.deletions],
  ];

  return (
    <>
      <div className="admin-tabs" role="tablist">
        {tabs.map(([key, label, n]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={`admin-tab${tab === key ? " on" : ""}`} onClick={() => go(key)}>
            {label}{n > 0 && <span className={`tab-count${key === "errors" ? " tab-count-red" : ""}`}>{n}</span>}
          </button>
        ))}
      </div>
      {tab === "businesses" && (
        <>
          {custom.length > 0 && <CustomRequests rows={custom} />}
          <Businesses plans={plans} tenants={tenants} requests={requests} />
        </>
      )}
      {tab === "plans" && <Plans plans={plans} />}
      {tab === "errors" && <Errors />}
      {tab === "deletion" && <Deletions />}
    </>
  );
}

// ── Custom plan requests: send a price; the business accepts from its Plan page

function CustomRequests({ rows }: { rows: CustomRequest[] }) {
  const { t, lang } = useI18n();
  const a = t.admin;
  const nf = new Intl.NumberFormat(lang);
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<Record<string, boolean>>({});

  async function run(id: string, fn: () => Promise<unknown>) {
    setBusy(id);
    try {
      await fn();
      setEditing((e) => ({ ...e, [id]: false }));
      router.refresh();
    } catch {
      window.alert(a.actionError);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card">
      <h2>{a.customRequests} ({nf.format(rows.length)})</h2>
      {rows.map((r) => {
        const price = prices[r.id] ?? (r.offer_price != null ? String(r.offer_price) : "");
        const asking = r.status === "open" || editing[r.id];
        return (
          <div key={r.id} className="cr">
            <div className="cr-top">
              <b>{r.tenant}</b>
              {r.current && <span className="pill">{r.current}</span>}
              <span className="hint">{new Date(r.created_at).toLocaleDateString(lang)}</span>
            </div>
            <div className="cr-terms">
              {fill(a.customTerms, { conv: nf.format(r.conversations), kb: nf.format(r.kb_chars), seats: r.seats })}
            </div>
            {r.notes && <div className="cr-notes" dir="auto">{r.notes}</div>}
            <div className="cr-act">
              {asking ? (
                <>
                  <span dir="ltr">$</span>
                  <input dir="ltr" inputMode="decimal" aria-label={a.price} value={price}
                    onChange={(e) => setPrices((p) => ({ ...p, [r.id]: e.target.value.replace(/[^\d.]/g, "") }))} />
                  <span className="hint">/ {a.monthShort}</span>
                  <button className="btn btn-sm" disabled={!!busy || !(Number(price) > 0)}
                    onClick={() => run(r.id, () => api(`/admin/custom/${r.id}/offer`, { method: "POST", body: JSON.stringify({ price_usd: Number(price) }) }))}>
                    {a.sendOffer}
                  </button>
                </>
              ) : (
                <>
                  <span className={`pill ${r.expired ? "pill-error" : "pill-on"}`}>
                    {r.expired ? a.offerExpired : fill(a.offerSent, {
                      price: nf.format(r.offer_price ?? 0), date: new Date(r.offer_expires_at!).toLocaleDateString(lang) })}
                  </span>
                  <button className="link-btn" onClick={() => setEditing((e) => ({ ...e, [r.id]: true }))}>{a.changePrice}</button>
                </>
              )}
              <button className="link-btn" disabled={!!busy}
                onClick={() => run(r.id, () => api(`/admin/custom/${r.id}/dismiss`, { method: "POST" }))}>{a.dismiss}</button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Businesses and plan requests

function Businesses({ plans, tenants, requests }: { plans: Plan[]; tenants: Tenant[]; requests: PlanRequest[] }) {
  const { t, lang } = useI18n();
  const a = t.admin;
  const nf = new Intl.NumberFormat(lang);
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const assignable = plans.filter((p) => p.active);

  async function run(id: string, fn: () => Promise<unknown>) {
    setBusy(id);
    try {
      await fn();
      router.refresh();
    } catch {
      window.alert(a.actionError);
    } finally {
      setBusy(null);
    }
  }

  function setPlan(tenantId: string, business: string, planId: string) {
    const plan = plans.find((p) => p.id === planId);
    if (!plan || !window.confirm(fill(a.confirmPlan, { business, plan: plan.name }))) return;
    run(tenantId, () => api(`/admin/tenants/${tenantId}/plan`, { method: "POST", body: JSON.stringify({ plan_id: planId }) }));
  }

  function bonus(x: Tenant) {
    const raw = window.prompt(fill(a.bonusPrompt, { business: x.name }), "50");
    const amount = Number(raw);
    if (!raw || !Number.isInteger(amount) || amount === 0) return;
    run(x.id, () => api(`/admin/tenants/${x.id}/bonus`, { method: "POST", body: JSON.stringify({ amount }) }));
  }

  function toggleStatus(x: Tenant) {
    const next = x.status === "active" ? "suspended" : "active";
    if (next === "suspended" && !window.confirm(fill(a.confirmSuspend, { business: x.name }))) return;
    run(x.id, () => api(`/admin/tenants/${x.id}/status`, { method: "POST", body: JSON.stringify({ status: next }) }));
  }

  return (
    <>
      {requests.length > 0 && (
        <div className="card">
          <h2>{a.requests} ({nf.format(requests.length)})</h2>
          <div className="table-wrap">
            <table className="grid">
              <thead><tr><th>{a.name}</th><th>{a.currentPlan}</th><th>{a.requestedPlan}</th><th>{a.date}</th><th /></tr></thead>
              <tbody>
                {requests.map((r) => (
                  <tr key={r.id}>
                    <td>{r.tenant}</td>
                    <td>{r.current ?? "—"}</td>
                    <td><b>{r.plan}</b></td>
                    <td>{new Date(r.created_at).toLocaleDateString(lang)}</td>
                    <td>
                      <div className="req-actions">
                        <button className="btn btn-sm" disabled={!!busy} onClick={() => setPlan(r.tenant_id, r.tenant, r.plan_id)}>{a.approve}</button>
                        <button className="btn btn-sm btn-secondary" disabled={!!busy}
                          onClick={() => run(r.id, () => api(`/admin/requests/${r.id}/dismiss`, { method: "POST" }))}>{a.dismiss}</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card">
        <h2>{a.tenants} ({nf.format(tenants.length)})</h2>
        <div className="table-wrap">
          <table className="grid">
            <thead>
              <tr><th>{a.name}</th><th>{a.plan}</th><th>{a.usage}</th><th>{a.channels}</th><th>{a.team}</th><th>{a.status}</th><th>{a.created}</th></tr>
            </thead>
            <tbody>
              {tenants.map((x) => (
                <tr key={x.id} className={x.status === "suspended" ? "row-suspended" : undefined}>
                  <td>{x.name}</td>
                  <td>
                    <select className="plan-select" value={x.plan_id ?? ""} disabled={busy === x.id}
                      onChange={(e) => setPlan(x.id, x.name, e.target.value)}>
                      {!x.plan_id && <option value="">—</option>}
                      {x.plan_id && !assignable.some((p) => p.id === x.plan_id) && <option value={x.plan_id}>{x.plan}</option>}
                      {assignable.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                  </td>
                  <td className="nowrap">
                    <span className={x.quota && x.used >= x.quota ? "error-text" : undefined}>{nf.format(x.used)} / {nf.format(x.quota)}</span>
                    {x.bonus > 0 && <span className="hint"> (+{nf.format(x.bonus)})</span>}{" "}
                    <button className="link-btn" disabled={!!busy} onClick={() => bonus(x)}>{a.bonus}</button>
                  </td>
                  <td>
                    {x.channels.map((c) => <span key={c} className="pill pill-on ch-pill">{t.inbox.channelNames[c as "widget"] ?? c}</span>)}
                    {x.broken.map((c) => <span key={c} className="pill pill-error ch-pill">{t.inbox.channelNames[c as "widget"] ?? c}</span>)}
                    {!x.channels.length && !x.broken.length && <span className="hint">—</span>}
                  </td>
                  <td>{nf.format(x.members)}</td>
                  <td className="nowrap">
                    <span className={`pill ${x.status === "active" ? "pill-on" : "pill-error"}`}>{x.status === "active" ? a.active : a.suspended}</span>{" "}
                    <button className="link-btn" disabled={!!busy} onClick={() => toggleStatus(x)}>{x.status === "active" ? a.suspend : a.activate}</button>
                  </td>
                  <td>{new Date(x.created_at).toLocaleDateString(lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ── Plans

const EMPTY: Omit<Plan, "id" | "is_signup_default"> = {
  code: "", name: "", price_usd: 0, billing_period: "monthly", conversation_quota: 100, max_channels: 4,
  kb_char_limit: 50000, seats: 1, show_branding: true, is_public: true, active: true,
};

function Plans({ plans }: { plans: Plan[] }) {
  const { t, lang } = useI18n();
  const a = t.admin;
  const nf = new Intl.NumberFormat(lang);
  const router = useRouter();
  const [editing, setEditing] = useState<(Partial<Plan> & typeof EMPTY) | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    if (!editing) return;
    setBusy(true);
    setError("");
    const { id, code, is_signup_default, ...fields } = editing;
    try {
      if (id) {
        await api(`/admin/plans/${id}`, { method: "PUT", body: JSON.stringify(fields) });
      } else {
        await api("/admin/plans", { method: "POST", body: JSON.stringify({ ...fields, code }) });
      }
      setEditing(null);
      router.refresh();
    } catch (e) {
      const code = e instanceof ApiError ? (e.detail as { code?: string } | null)?.code : null;
      setError(code === "code_taken" ? a.codeTaken : code === "bad_code" ? a.codeHint : code === "signup_default" ? a.signupDefaultNote : a.planError);
    } finally {
      setBusy(false);
    }
  }

  async function quick(p: Plan, change: Partial<Plan>) {
    try {
      await api(`/admin/plans/${p.id}`, { method: "PUT", body: JSON.stringify(change) });
      router.refresh();
    } catch (e) {
      const code = e instanceof ApiError ? (e.detail as { code?: string } | null)?.code : null;
      window.alert(code === "signup_default" ? a.signupDefaultNote : a.planError);
    }
  }

  async function move(i: number, dir: -1 | 1) {
    const ids = plans.map((p) => p.id);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    await api("/admin/plans/order", { method: "POST", body: JSON.stringify({ ids }) });
    router.refresh();
  }

  const num = (k: keyof typeof EMPTY, label: string, step = 1) => (
    <div className="field">
      <label>{label}</label>
      <input type="number" min={0} step={step} dir="ltr" value={String(editing?.[k] ?? "")}
        onChange={(e) => setEditing((p) => p && { ...p, [k]: Number(e.target.value) })} />
    </div>
  );
  const check = (k: keyof typeof EMPTY, label: string) => (
    <label className="check">
      <input type="checkbox" checked={!!editing?.[k]} onChange={(e) => setEditing((p) => p && { ...p, [k]: e.target.checked })} />
      {label}
    </label>
  );

  return (
    <div className="card">
      <div className="card-head">
        <h2>{a.plans}</h2>
        <button className="btn btn-sm" onClick={() => { setError(""); setEditing({ ...EMPTY }); }}>+ {a.newPlan}</button>
      </div>
      <p className="hint">{a.planNote}</p>
      <div className="table-wrap">
        <table className="grid">
          <thead>
            <tr><th /><th>{a.name}</th><th>{a.price}</th><th>{a.quota}</th><th>{a.channels}</th><th>{a.kb}</th><th>{a.team}</th><th /><th /></tr>
          </thead>
          <tbody>
            {plans.map((p, i) => (
              <tr key={p.id} className={!p.active ? "row-suspended" : undefined}>
                <td className="nowrap order-btns">
                  <button className="icon-btn" aria-label={a.moveUp} disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
                  <button className="icon-btn" aria-label={a.moveDown} disabled={i === plans.length - 1} onClick={() => move(i, 1)}>↓</button>
                </td>
                <td>
                  <b>{p.name}</b> <span className="hint" dir="ltr">{p.code}</span>
                  <div className="plan-badges">
                    {p.is_signup_default && <span className="pill pill-on">{a.signupPlan}</span>}
                    {!p.is_public && <span className="pill pill-off">{a.hidden}</span>}
                    {!p.active && <span className="pill pill-error">{a.retired}</span>}
                    {!p.show_branding && <span className="pill pill-off">{a.noBranding}</span>}
                  </div>
                </td>
                <td className="nowrap" dir="ltr">${nf.format(p.price_usd)}{p.billing_period === "monthly" ? ` / ${a.monthShort}` : ""}</td>
                <td className="nowrap">
                  {nf.format(p.conversation_quota)}{" "}
                  {p.billing_period === "monthly" ? a.monthly
                    : p.billing_period === "trial" ? fill(a.trialFor, { n: p.trial_days ?? 14 }) : a.oneTime}
                </td>
                <td>{p.max_channels}</td>
                <td>{nf.format(p.kb_char_limit)}</td>
                <td>{p.seats}</td>
                <td className="nowrap">
                  <button className="link-btn" onClick={() => quick(p, { is_public: !p.is_public })}>{p.is_public ? a.hide : a.show}</button>
                </td>
                <td><button className="btn btn-sm btn-secondary" onClick={() => { setError(""); setEditing({ ...p }); }}>{a.edit}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <div className="modal-bg" onClick={() => !busy && setEditing(null)}>
          <form className="modal plan-modal" onClick={(e) => e.stopPropagation()} onSubmit={(e) => { e.preventDefault(); save(); }}>
            <h3>{editing.id ? fill(a.editPlan, { plan: editing.name }) : a.newPlan}</h3>
            {!editing.id && (
              <div className="field">
                <label>{a.code}</label>
                <input dir="ltr" required maxLength={40} value={editing.code}
                  onChange={(e) => setEditing((p) => p && { ...p, code: e.target.value })} />
                <span className="hint">{a.codeHint}</span>
              </div>
            )}
            <div className="field">
              <label>{a.name}</label>
              <input required maxLength={60} value={editing.name} onChange={(e) => setEditing((p) => p && { ...p, name: e.target.value })} />
            </div>
            <div className="plan-form-grid">
              {num("price_usd", a.price, 0.01)}
              <div className="field">
                <label>{a.period}</label>
                <select value={editing.billing_period}
                  onChange={(e) => setEditing((p) => p && { ...p, billing_period: e.target.value as Plan["billing_period"] })}>
                  <option value="monthly">{a.monthly}</option>
                  <option value="one_time">{a.oneTime}</option>
                  <option value="trial">{a.trial}</option>
                </select>
              </div>
              {editing.billing_period === "trial" && (
                <div className="field">
                  <label>{a.trialDays}</label>
                  <input type="number" min={1} max={90} dir="ltr" value={editing.trial_days ?? 14}
                    onChange={(e) => setEditing((p) => p && { ...p, trial_days: Number(e.target.value) })} />
                </div>
              )}
              {num("conversation_quota", a.quota)}
              {num("max_channels", a.channels)}
              {num("kb_char_limit", a.kb, 1000)}
              {num("seats", a.team)}
            </div>
            <div className="plan-checks">
              {check("show_branding", a.brandingOn)}
              {check("is_public", a.publicOn)}
              {check("active", a.activeOn)}
            </div>
            {editing.id && <p className="hint">{a.planNote}</p>}
            {error && <p className="error-text">{error}</p>}
            <div className="actions">
              {editing.id && !editing.is_signup_default && editing.active && (
                <button type="button" className="link-btn me-auto" onClick={() => { quick(editing as Plan, { is_signup_default: true }); setEditing(null); }}>
                  {a.makeSignup}
                </button>
              )}
              <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => setEditing(null)}>{a.cancel}</button>
              <button className="btn" disabled={busy}>{a.save}</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

// ── Errors

function Errors() {
  const { t, lang } = useI18n();
  const a = t.admin;
  const nf = new Intl.NumberFormat(lang);
  const [rows, setRows] = useState<ErrorRow[] | null>(null);
  const load = useCallback(async () => setRows(await api<ErrorRow[]>("/admin/errors")), []);
  useEffect(() => { load().catch(() => setRows([])); }, [load]);

  async function fix(id?: number) {
    if (id === undefined && !window.confirm(a.confirmClear)) return;
    await api(id === undefined ? "/admin/errors" : `/admin/errors/${id}`, { method: "DELETE" });
    await load();
  }

  if (!rows) return <div className="card"><p className="hint">…</p></div>;
  return (
    <div className="card">
      <div className="card-head">
        <h2>{a.errors} ({nf.format(rows.length)})</h2>
        {rows.length > 0 && <button className="btn btn-sm btn-secondary" onClick={() => fix()}>{a.clearAll}</button>}
      </div>
      <p className="hint">{a.errorsNote}</p>
      {rows.length === 0 && <p className="empty-ok">{a.noErrors}</p>}
      <div className="err-list">
        {rows.map((e) => (
          <div key={e.id} className="err-item">
            <div className="err-top">
              <span className={`pill err-kind err-${e.kind}`}>{e.kind}</span>
              <b dir="ltr">{e.where}</b>
              {e.business && <span className="hint">· {e.business}</span>}
              <span className="err-count">{fill(a.times, { n: nf.format(e.count) })}</span>
            </div>
            <div className="err-msg" dir="ltr">{e.message}</div>
            <div className="err-foot">
              <span className="hint">{a.lastSeen} {new Date(e.last_at).toLocaleString(lang)} · {a.firstSeen} {new Date(e.first_at).toLocaleString(lang)}</span>
              <button className="link-btn" onClick={() => fix(e.id)}>{a.markFixed}</button>
            </div>
            {e.detail && (
              <details>
                <summary>{a.details}</summary>
                <pre dir="ltr">{e.detail}</pre>
              </details>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Data-deletion requests

function Deletions() {
  const { t, lang } = useI18n();
  const a = t.admin;
  const [rows, setRows] = useState<Deletion[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(async () => setRows(await api<Deletion[]>("/admin/deletion-requests")), []);
  useEffect(() => { load().catch(() => setRows([])); }, [load]);

  async function act(d: Deletion, action: "delete-data" | "dismiss") {
    if (action === "delete-data" && !window.confirm(fill(a.confirmDeleteData, { n: d.matches.length }))) return;
    setBusy(d.id);
    try {
      await api(`/admin/deletion-requests/${d.id}/${action}`, { method: "POST" });
      await load();
    } finally {
      setBusy(null);
    }
  }

  if (!rows) return <div className="card"><p className="hint">…</p></div>;
  return (
    <div className="card">
      <h2>{a.deletion}</h2>
      <p className="hint">{a.deletionNote}</p>
      {rows.length === 0 && <p className="empty-ok">{a.noRequests}</p>}
      <div className="err-list">
        {rows.map((d) => (
          <div key={d.id} className={`err-item${d.status !== "open" ? " del-closed" : ""}`}>
            <div className="err-top">
              <span className={`pill ${d.status === "open" ? "pill-error" : "pill-off"}`}>
                {d.status === "open" ? a.openLabel : d.status === "done" ? fill(a.doneDeleted, { n: d.deleted_count ?? 0 }) : a.dismissedLabel}
              </span>
              <b dir="ltr">{d.contact}</b>
              {d.name && <span>· {d.name}</span>}
              <span className="err-count" dir="ltr">{d.code}</span>
            </div>
            {(d.business || d.details) && (
              <div className="err-msg">{d.business && <><b>{a.business}:</b> {d.business}. </>}{d.details}</div>
            )}
            {d.status === "open" && (
              <div className="del-matches">
                {d.matches.length === 0 ? <span className="hint">{a.noMatches}</span> : (
                  <>
                    <span>{fill(a.matches, { n: d.matches.length })}</span>
                    <ul>{d.matches.map((m, i) => <li key={i}>{m.business}: {m.name ?? "—"} <span className="hint" dir="ltr">{m.handle}</span></li>)}</ul>
                  </>
                )}
              </div>
            )}
            <div className="err-foot">
              <span className="hint">{new Date(d.created_at).toLocaleString(lang)}</span>
              {d.status === "open" && (
                <span className="req-actions">
                  {d.matches.length > 0 && (
                    <button className="btn btn-sm btn-danger" disabled={!!busy} onClick={() => act(d, "delete-data")}>
                      {fill(a.deleteData, { n: d.matches.length })}
                    </button>
                  )}
                  <button className="btn btn-sm btn-secondary" disabled={!!busy} onClick={() => act(d, "dismiss")}>{a.dismiss}</button>
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
