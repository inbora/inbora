import { notFound } from "next/navigation";
import AdminTenants from "@/components/AdminTenants";
import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";
import { getMe } from "@/lib/me";

type Plan = {
  id: string;
  code: string;
  name: string;
  price_usd: number;
  billing_period: "one_time" | "monthly";
  conversation_quota: number;
  max_channels: number;
  kb_char_limit: number;
  active: boolean;
};
type Tenant = { id: string; name: string; slug: string; status: string; created_at: string; plan: string | null;
  plan_id: string | null; used: number; quota: number };
type Request = { id: string; tenant_id: string; tenant: string; plan_id: string; plan: string; current: string | null; created_at: string };

export default async function AdminPage() {
  const { t, lang } = await getI18n();
  const me = await getMe();
  if (!me?.user.is_super_admin) notFound();

  const data = await apiGet<{ plans: Plan[]; tenants: Tenant[]; requests: Request[] }>("/admin/overview");
  const nf = new Intl.NumberFormat(lang);

  return (
    <>
      <h1>{t.admin.title}</h1>
      <p className="hint">{t.admin.editSoon}</p>

      <AdminTenants plans={(data?.plans ?? []).map((p) => ({ id: p.id, name: p.name }))}
        tenants={data?.tenants ?? []} requests={data?.requests ?? []} />

      <div className="card">
        <h2>{t.admin.plans}</h2>
        <div className="table-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th>{t.admin.name}</th>
                <th>{t.admin.price}</th>
                <th>{t.admin.period}</th>
                <th>{t.admin.quota}</th>
                <th>{t.admin.channels}</th>
                <th>{t.admin.kb}</th>
              </tr>
            </thead>
            <tbody>
              {(data?.plans ?? []).map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td>{nf.format(p.price_usd)}</td>
                  <td>{p.billing_period === "monthly" ? t.admin.monthly : t.admin.oneTime}</td>
                  <td>{nf.format(p.conversation_quota)}</td>
                  <td>{nf.format(p.max_channels)}</td>
                  <td>{nf.format(p.kb_char_limit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

    </>
  );
}
