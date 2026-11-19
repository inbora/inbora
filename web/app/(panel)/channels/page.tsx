import { Suspense } from "react";
import ChannelsManager, { type ChannelsData } from "@/components/ChannelsManager";
import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";
import { getMe } from "@/lib/me";

export default async function ChannelsPage() {
  const { t } = await getI18n();
  const [data, me] = await Promise.all([apiGet<ChannelsData>("/channels"), getMe()]);
  return (
    <>
      <h1>{t.nav.channels}</h1>
      <p className="hint">{t.panel.channelsIntro}</p>
      {data && (
        <Suspense>
          <ChannelsManager initial={data} branding={me?.plan?.show_branding ?? true} />
        </Suspense>
      )}
    </>
  );
}
