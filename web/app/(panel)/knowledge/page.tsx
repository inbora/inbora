import ComingSoon from "@/components/ComingSoon";
import { getI18n } from "@/lib/i18n/server";

export default async function Page() {
  const { t } = await getI18n();
  return <ComingSoon title={t.nav.knowledge} intro={t.panel.knowledgeIntro} step={3} />;
}
