import PlanPicker from "@/components/PlanPicker";
import { getI18n } from "@/lib/i18n/server";
import { getMe } from "@/lib/me";

export default async function PlanPage() {
  const { t, lang } = await getI18n();
  const me = await getMe();
  const plan = me?.plan;
  const nf = new Intl.NumberFormat(lang);

  if (!plan) {
    return <h1>{t.plan.title}</h1>;
  }

  const pct = plan.conversation_quota
    ? Math.min(100, Math.round((plan.conversations_used / plan.conversation_quota) * 100))
    : 0;
  const full = plan.conversations_used >= plan.conversation_quota;
  const monthly = plan.billing_period === "monthly";

  return (
    <>
      <h1>
        {t.plan.title}: {plan.name}
      </h1>
      <div className="card">
        <h2>{t.plan.conversations}</h2>
        <div className="meter" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <span className={full ? "meter-full" : undefined} style={{ width: `${pct}%` }} />
        </div>
        <div className="hint">
          {nf.format(plan.conversations_used)} {t.plan.used} {t.plan.of} {nf.format(plan.conversation_quota)}{" "}
          {monthly ? t.plan.perMonth : t.plan.total}
          {monthly && plan.period_end && (
            <>
              {" · "}
              {t.plan.renews} {new Date(plan.period_end).toLocaleDateString(lang)}
            </>
          )}
        </div>
        {full && <p className="plan-full">{t.plan.fullNote}</p>}
      </div>
      <PlanPicker />
    </>
  );
}
