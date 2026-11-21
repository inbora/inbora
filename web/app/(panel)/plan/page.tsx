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

  if (plan.billing_period === "trial") {
    const daysLeft = plan.trial_ends_at ? Math.max(0, Math.ceil((Date.parse(plan.trial_ends_at) - Date.now()) / 86_400_000)) : 0;
    const used = Math.min(plan.conversations_used, plan.conversation_quota || plan.conversations_used);
    const tpct = plan.conversation_quota ? Math.min(100, Math.round((used / plan.conversation_quota) * 100)) : 100;
    return (
      <>
        <h1>{t.plan.title}: {t.plan.trialBadge}</h1>
        <div className={`card trial-card${plan.trial_ended ? " trial-ended" : ""}`}>
          {plan.trial_ended ? (
            <>
              <h2>{t.plan.trialEnded}</h2>
              <p className="hint">{t.plan.trialEndedHint}</p>
            </>
          ) : (
            <>
              <div className="trial-head">
                <span className="trial-pill">{t.plan.trialBadge}</span>
                <b>{daysLeft <= 1 ? t.plan.lastDay : t.plan.daysLeft.replace("{n}", nf.format(daysLeft))}</b>
              </div>
              <div className="meter" role="progressbar" aria-valuenow={tpct} aria-valuemin={0} aria-valuemax={100}>
                <span className={tpct >= 100 ? "meter-full" : undefined} style={{ width: `${tpct}%` }} />
              </div>
              <div className="hint">
                {t.plan.trialUsage.replace("{used}", nf.format(used)).replace("{quota}", nf.format(plan.conversation_quota))}
                {" · "}{t.plan.trialHint}
              </div>
            </>
          )}
        </div>
        <PlanPicker />
      </>
    );
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
