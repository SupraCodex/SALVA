import { RiskIcon } from "../../components/charts";
import { ErrorState, Skeleton } from "../../components/ui";
import { dateTime, fcfa, kg, pct } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";
import type { LotHistory } from "../../lib/types";
import type { LotContext } from "../LotHub";

export function HistoryView({ ctx }: { ctx: LotContext }) {
  const { t, lang } = useI18n();
  const history = useApi<LotHistory>(`/lots/${ctx.lot.id}/history`);
  if (history.error) return <ErrorState error={history.error} onRetry={history.reload} />;
  if (!history.data) return <Skeleton lines={4} />;
  const h = history.data;
  return (
    <div className="history">
      <section className="panel">
        <h2>{t("history.lotTitle")}</h2>
        {h.analyses.length === 0 && <p>{t("history.empty")}</p>}
        <ol className="timeline">
          {h.analyses.map((a) => (
            <li key={a.id}>
              <p className="timeline__title">
                {t("history.analysis", { date: dateTime(a.analysis_at, lang) })}{" "}
                {a.replay && <span className="tag">{t("analysis.replayBadge", { date: dateTime(a.analysis_at, lang) })}</span>}
              </p>
              <p>
                <span className={`risk-pill risk-pill--${a.risk_level}`}>
                  <RiskIcon level={a.risk_level} /> {t(`analysis.level.${a.risk_level}`)}
                </span>{" "}
                {pct(a.loss_p10, lang)} – {pct(a.loss_p90, lang)}
              </p>
              <ul className="timeline__subs">
                {a.simulations.map((s) => (
                  <li key={s.id}>
                    {t("history.simulation", {
                      profile: t(`sim.profile.${s.risk_profile}`),
                      action: s.no_clear_winner ? t("dash.noWinner") : s.best_action ? t(`action.${s.best_action}`) : t("action.none"),
                    })}
                    {s.user_overrides > 0 && <span className="muted"> — {t("history.overrides", { n: s.user_overrides })}</span>}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </section>
      <section className="panel">
        <h2>{t("history.outcomes")}</h2>
        {h.outcomes.length === 0 ? (
          <p>{t("history.noOutcome")}</p>
        ) : (
          <ul className="outcomes">
            {h.outcomes.map((o) => (
              <li key={o.id}>
                <strong>{t(`action.${o.decision_taken}`)}</strong> — {dateTime(o.recorded_at, lang)}
                {o.followed_reco !== null && <span className="muted"> — {o.followed_reco ? t("reco.followed") : t("reco.notFollowed")}</span>}
                {(o.actual_recovered_kg !== null || o.actual_revenue_fcfa !== null) && (
                  <span> — {kg(o.actual_recovered_kg, lang)}, {fcfa(o.actual_revenue_fcfa, lang)}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
