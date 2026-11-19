import AgentSettingsForm, { type AgentSettings } from "@/components/AgentSettingsForm";
import AgentTestChat from "@/components/AgentTestChat";
import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";

export default async function AgentPage() {
  const { t } = await getI18n();
  const settings = await apiGet<AgentSettings>("/agent/settings");
  return (
    <>
      <h1>{t.nav.agent}</h1>
      <div className="agent-layout">
        {settings && <AgentSettingsForm initial={settings} />}
        <AgentTestChat />
      </div>
    </>
  );
}
