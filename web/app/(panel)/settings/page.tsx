import LanguageSwitcher from "@/components/LanguageSwitcher";
import NotificationSettings from "@/components/NotificationSettings";
import ProfileNameForm from "@/components/ProfileNameForm";
import { getI18n } from "@/lib/i18n/server";
import { getMe } from "@/lib/me";

export default async function SettingsPage() {
  const { t } = await getI18n();
  const me = await getMe();

  return (
    <>
      <h1>{t.nav.settings}</h1>
      <p className="hint">{t.panel.settingsIntro}</p>
      <div className="card">
        <dl className="kv">
          <dt>{t.settings.account}</dt>
          <dd dir="ltr">{me?.user.email ?? "—"}</dd>
          <dt>{t.settings.yourName}</dt>
          <dd>
            <ProfileNameForm initial={me?.user.full_name ?? ""} />
            <span className="hint">{t.settings.yourNameHint}</span>
          </dd>
          <dt>{t.settings.business}</dt>
          <dd>{me?.tenant.name ?? "—"}</dd>
          <dt>{t.settings.businessId}</dt>
          <dd dir="ltr">{me?.tenant.slug ?? "—"}</dd>
          <dt>{t.settings.language}</dt>
          <dd>
            <LanguageSwitcher />
          </dd>
        </dl>
      </div>
      <NotificationSettings email={me?.user.email ?? ""} />
    </>
  );
}
