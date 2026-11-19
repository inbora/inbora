import AgentTestChat from "@/components/AgentTestChat";
import { getI18n } from "@/lib/i18n/server";

export default async function AgentPage() {
  const { t } = await getI18n();
  return (
    <>
      <h1>{t.nav.agent}</h1>
      <p className="hint">{t.agentPage.settingsSoon}</p>
      <AgentTestChat />
    </>
  );
}
