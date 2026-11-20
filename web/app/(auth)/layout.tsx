import Link from "next/link";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import Logo from "@/components/Logo";
import { getI18n } from "@/lib/i18n/server";

export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const { t } = await getI18n();
  return (
    <div className="auth-wrap">
      <div className="auth-top">
        <LanguageSwitcher />
      </div>
      <div className="auth-card">
        <div className="auth-brand">
          <Logo /> {t.appName}
        </div>
        <div className="auth-tagline">{t.tagline}</div>
        {children}
        <div className="auth-legal">
          <Link href="/terms">{t.auth.terms}</Link>
          <Link href="/privacy">{t.auth.privacy}</Link>
        </div>
      </div>
    </div>
  );
}
