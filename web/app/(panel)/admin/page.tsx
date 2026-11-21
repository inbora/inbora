import { notFound } from "next/navigation";
import AdminConsole, { type CustomRequest, type Plan, type PlanRequest, type Tenant } from "@/components/AdminConsole";
import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";
import { getMe } from "@/lib/me";

type Overview = { plans: Plan[]; tenants: Tenant[]; requests: PlanRequest[]; custom?: CustomRequest[];
  counts: { errors: number; deletions: number } };
const TABS = ["businesses", "plans", "errors", "deletion"] as const;

export default async function AdminPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { t } = await getI18n();
  const me = await getMe();
  if (!me?.user.is_super_admin) notFound();

  const data = await apiGet<Overview>("/admin/overview");
  const tab = (await searchParams).tab;
  const initialTab = (TABS as readonly string[]).includes(tab ?? "") ? (tab as (typeof TABS)[number]) : "businesses";

  return (
    <>
      <h1>{t.admin.title}</h1>
      {!data ? (
        <div className="alert alert-warn">{t.panel.apiDown}</div>
      ) : (
        <AdminConsole plans={data.plans} tenants={data.tenants} requests={data.requests} custom={data.custom ?? []}
          counts={data.counts ?? { errors: 0, deletions: 0 }} initialTab={initialTab} />
      )}
    </>
  );
}
