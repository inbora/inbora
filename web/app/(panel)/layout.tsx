import Sidebar from "@/components/Sidebar";
import { getI18n } from "@/lib/i18n/server";
import { getMe } from "@/lib/me";
import { createClient } from "@/lib/supabase/server";

export default async function PanelLayout({ children }: { children: React.ReactNode }) {
  const { t } = await getI18n();
  const me = await getMe();

  // Fallback when the API is unreachable: still show who is logged in.
  let email = me?.user.email ?? "";
  if (!me) {
    const supabase = await createClient();
    const { data } = await supabase.auth.getUser();
    email = data.user?.email ?? "";
  }

  return (
    <div className="shell">
      <Sidebar isAdmin={!!me?.user.is_super_admin} />
      <div className="main">
        <header className="topbar">
          <div className="topbar-title">{me?.tenant.name ?? t.appName}</div>
          <div className="topbar-meta">
            {me?.user.is_super_admin && <span className="badge badge-admin">{t.nav.admin}</span>}
            {me?.plan && <span className="badge">{me.plan.name}</span>}
            <span dir="ltr">{email}</span>
          </div>
        </header>
        <main className="content">
          {!me && <div className="alert alert-warn">{t.panel.apiDown}</div>}
          {children}
        </main>
      </div>
    </div>
  );
}
