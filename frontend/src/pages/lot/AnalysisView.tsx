import { useState } from "react";

import { FactorList, RiskGauge } from "../../components/charts";
import { ErrorState, Field, Input, Notice, SourceBadge, Spinner } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { dateTime, fcfa, fromLocalInput, hours, num, toLocalInput } from "../../lib/format";
import { toApiError } from "../../lib/hooks";
import { fieldErrors, useI18n } from "../../lib/i18n";
import { Link } from "../../lib/router";
import type { Analysis } from "../../lib/types";
import type { LotContext } from "../LotHub";

export function AnalysisView({ ctx }: { ctx: LotContext }) {
  const { t, td, lang } = useI18n();
  const { lot, analysis } = ctx;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [replay, setReplay] = useState(false);
  const [replayAt, setReplayAt] = useState(() => toLocalInput(analysis?.analysis_at ?? new Date()));
  const [replayError, setReplayError] = useState<string | undefined>();

  const run = async () => {
    setBusy(true);
    setError(null);
    setReplayError(undefined);
    try {
      const body = replay ? { analysis_at: fromLocalInput(replayAt) } : {};
      const result = await api<Analysis>(`/lots/${lot.id}/analyses`, { method: "POST", body });
      ctx.setAnalysis(result);
    } catch (err) {
      const e = toApiError(err);
      const fields = fieldErrors(e.errors, td);
      if (fields.analysis_at) setReplayError(fields.analysis_at);
      else setError(e);
    } finally {
      setBusy(false);
    }
  };

  const controls = lot.status !== "closed" && (
    <div className="run-box">
      <label className="check">
        <input type="checkbox" checked={replay} onChange={(e) => setReplay(e.target.checked)} />
        {t("analysis.replay")}
      </label>
      {replay && (
        <Field label={t("analysis.replayAt")} error={replayError}>
          {(p) => <Input {...p} type="datetime-local" value={replayAt} onChange={(e) => setReplayAt(e.target.value)} />}
        </Field>
      )}
      <button type="button" className="button button--primary" onClick={run} disabled={busy}>
        {analysis ? t("analysis.rerun") : t("analysis.run")}
      </button>
    </div>
  );

  if (busy) return <Spinner label={t("analysis.running")} />;
  if (!analysis) {
    return (
      <section className="panel">
        <p>{t("analysis.none")}</p>
        {error && <ErrorState error={error} />}
        {controls}
      </section>
    );
  }

  const q = analysis.risk.loss_fraction;
  const i = analysis.inputs;
  return (
    <div className="analysis">
      {error && <ErrorState error={error} />}
      <section className="panel panel--risk" aria-labelledby="risk-title">
        <div className="panel__head">
          <h2 id="risk-title">{t("analysis.riskTitle")}</h2>
          {analysis.replay && <span className="tag">{t("analysis.replayBadge", { date: dateTime(analysis.analysis_at, lang) })}</span>}
        </div>
        <RiskGauge p10={q.p10 ?? 0} p50={q.p50 ?? 0} p90={q.p90 ?? 1} level={analysis.risk.level} />
        {analysis.shelf_life_p50_h !== null &&
          (analysis.shelf_life_p50_h <= 0 ? (
            <Notice tone="warn">{t("analysis.shelfLifeOver")}</Notice>
          ) : (
            <p>{t("analysis.shelfLife", { h: hours(analysis.shelf_life_p50_h, lang) })}</p>
          ))}
        {analysis.risk.level === "low" && <Notice tone="ok">{t("analysis.lowRisk")}</Notice>}
        {analysis.model.fallback && <Notice tone="warn">{t("analysis.fallback")}</Notice>}
        {analysis.extrapolated_features.length > 0 && (
          <Notice tone="warn">{t("analysis.extrapolated", { fields: analysis.extrapolated_features.join(", ") })}</Notice>
        )}
      </section>

      <div className="split">
        <section className="panel" aria-labelledby="factors-title">
          <h2 id="factors-title">{t("analysis.factorsTitle")}</h2>
          <FactorList factors={analysis.top_factors} />
          <p className="muted small">{t("analysis.factorsNote")}</p>
        </section>
        <section className="panel" aria-labelledby="data-title">
          <h2 id="data-title">{t("analysis.dataTitle")}</h2>
          <dl className="facts">
            <div>
              <dt>{t("analysis.age")}</dt>
              <dd>{hours(i.age_h, lang)}</dd>
            </div>
            <div>
              <dt>{t("analysis.remaining")}</dt>
              <dd>{hours(i.remaining_transit_h, lang)}</dd>
            </div>
            <div>
              <dt>{t("analysis.delayRow")}</dt>
              <dd>{hours(i.delay_h, lang)}</dd>
            </div>
            <div>
              <dt>{t("analysis.temp")}</dt>
              <dd>
                {num(i.temp_mean_c.value, lang)} °C <SourceBadge source={i.temp_mean_c.source} />
              </dd>
            </div>
            <div>
              <dt>{t("analysis.productTemp")}</dt>
              <dd>{num(i.product_temp_mean_c, lang)} °C</dd>
            </div>
            <div>
              <dt>{t("analysis.price")}</dt>
              <dd>
                {fcfa(i.price_fcfa_kg.value, lang)}/kg <SourceBadge source={i.price_fcfa_kg.source} />
              </dd>
            </div>
          </dl>
          <p className="muted small">{t("analysis.model", { name: td(`dash.model.${analysis.model.name}`, analysis.model.name), version: analysis.model.version })}</p>
        </section>
      </div>

      <div className="next-step">
        {controls}
        <div className="row-actions">
          <Link to="/assumptions" className="button button--quiet">
            {t("analysis.seeAssumptions")}
          </Link>
          <button type="button" className="button button--primary" onClick={() => ctx.go("simulation")}>
            {t("analysis.simulate")}
          </button>
        </div>
      </div>
    </div>
  );
}
