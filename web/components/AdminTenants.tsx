"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

type PlanOpt = { id: string; name: string };
type Tenant = { id: string; name: string; status: string; created_at: string; plan: string | null; plan_id: string | null; used: number; quota: number };
type Request = { id: string; tenant_id: string; tenant: string; plan_id: string; plan: string; current: string | null; created_at: string };

const fill = (s: string, v: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

/** Plan requests and the businesses list, with changing a business's plan. */
export default function AdminTenants({ plans, tenants, requests }: { plans: PlanOpt[]; tenants: Tenant[]; requests: Request[] }) {
  const { t, lang } = useI18n();
  const a = t.admin;
  const nf = new Intl.NumberFormat(lang);
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);

  async function setPlan(tenantId: string, business: string, planId: string) {
    const plan = plans.find((p) => p.id === planId);
    if (!plan || !window.confirm(fill(a.confirmPlan, { business, plan: plan.name }))) return;
    setBusy(tenantId);
    try {
      await api(`/admin/tenants/${tenantId}/plan`, { method: "POST", body: JSON.stringify({ plan_id: planId }) });
      router.refresh();
    } finally {
      setBusy(null);
    }
  }

  async function dismiss(id: string) {
    setBusy(id);
    try {
      await api(`/admin/requests/${id}/dismiss`, { method: "POST" });
      router.refresh();
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      {requests.length > 0 && (
        <div className="card">
          <h2>{a.requests} ({nf.format(requests.length)})</h2>
          <div className="table-wrap">
            <table className="grid">
              <thead>
                <tr><th>{a.name}</th><th>{a.currentPlan}</th><th>{a.requestedPlan}</th><th>{a.date}</th><th /></tr>
              </thead>
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
                        <button className="btn btn-sm btn-secondary" disabled={!!busy} onClick={() => dismiss(r.id)}>{a.dismiss}</button>
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
              <tr><th>{a.name}</th><th>{a.plan}</th><th>{a.usage}</th><th>{a.status}</th><th>{a.created}</th></tr>
            </thead>
            <tbody>
              {tenants.map((x) => (
                <tr key={x.id}>
                  <td>{x.name}</td>
                  <td>
                    <select className="plan-select" value={x.plan_id ?? ""} disabled={busy === x.id}
                      onChange={(e) => setPlan(x.id, x.name, e.target.value)}>
                      {!x.plan_id && <option value="">—</option>}
                      {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                  </td>
                  <td className={x.quota && x.used >= x.quota ? "error-text" : undefined}>
                    {nf.format(x.used)} / {nf.format(x.quota)}
                  </td>
                  <td>{x.status}</td>
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
