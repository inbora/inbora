import { getI18n } from "@/lib/i18n/server";

export default async function ComingSoon({
  title,
  intro,
  step,
}: {
  title: string;
  intro: string;
  step: number;
}) {
  const { t } = await getI18n();
  return (
    <>
      <h1>{title}</h1>
      <div className="card empty">
        <p>{intro}</p>
        <span className="step">
          {t.panel.comingSoon} {step}
        </span>
      </div>
    </>
  );
}
