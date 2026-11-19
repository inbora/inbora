import ComingSoon from "@/components/ComingSoon";
import { getI18n } from "@/lib/i18n/server";

export default async function Page() {
  const { t } = await getI18n();
  return <ComingSoon title={t.nav.channels} intro={t.panel.channelsIntro} step={5} />;
}
