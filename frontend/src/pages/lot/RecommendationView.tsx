import { useEffect, useState, type FormEvent } from "react";

import { AskPanel } from "../../components/AskPanel";
import { AllocationBar } from "../../components/charts";
import { ScenarioCard } from "../../components/scenarios";
import { ErrorState, Field, Input, Notice, Select, Spinner } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { fcfa, kg, pct } from "../../lib/format";
import { toApiError, useApi } from "../../lib/hooks";
import { Link } from "../../lib/router";
import { fieldErrors, useI18n } from "../../lib/i18n";
import type { Action, Explanation, LotHistory, Outcome } from "../../lib/types";
import type { LotContext } from "../LotHub";

function ExplanationPanel({ recommendationId }: { recommendationId: string }) {
  const { t, lang } = useI18n();
  const [data, setData] = useState<Explanation | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api<Explanation>(`/recommendations/${recommendationId}/explanations`, { method: "POST", body: { lang } })
      .then((value) => !cancelled && setData(value))
      .catch((err) => !cancelled && setError(toApiError(err)));
    return () => {
      cancelled = true;
    };
  }, [recommendationId, lang, tick]);

  return (
    <section className="panel explanation" aria-labelledby="explanation-title" aria-live="polite">
      <div className="panel__head">
        <h2 id="explanation-title">{t("reco.explanationTitle")}</h2>
        {data && (
          <span className={`tag ${data.source === "llm" ? "tag--ai" : ""}`}>
            {data.source === "llm" ? t("reco.sourceLlm") : t("reco.sourceTemplate")}
          </span>
        )}
      </div>
      {!data && !error && <Spinner label={t("reco.explaining")} />}
      {error && (
        <Notice tone="warn">
          {t("reco.explainError")}{" "}
          <button type="button" className="link-button" onClick={() => setTick((n) => n + 1)}>
            {t("reco.retry")}
          </button>
        </Notice>
      )}
      {data && (
        <div className="explanation__body">
          <p className="explanation__summary">{data.summary}</p>
          <p>{data.risk_explanation}</p>
          <p>{data.scenario_comparison}</p>
          <p>{data.recommendation_text}</p>
          <h3>{t("reco.caveats")}</h3>
          <ul>
            {data.caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function OutcomeForms({ ctx }: { ctx: LotContext }) {
  const { t, td, lang } = useI18n();
  const { lot, simulation } = ctx;
  const history = useApi<LotHistory>(`/lots/${lot.id}/history`);
  const reco = simulation?.recommendation;
  const [decision, setDecision] = useState<Action | "other">(reco?.best_action ?? "continue");
  const [recovered, setRecovered] = useState("");
  const [revenue, setRevenue] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiError | null>(null);
  const outcomes: Outcome[] = history.data?.outcomes ?? [];

  const scenarioFor = (action: string) =>
    action === reco?.best_action && reco?.best_scenario_id
      ? reco.best_scenario_id
      : simulation?.scenarios.find((s) => s.action === action && s.feasible)?.id;

  const send = async (withResult: boolean) => {
    setErrors({});
    setFailure(null);
    const body: Record<string, unknown> = { decision_taken: decision, simulation_id: simulation?.id };
    const scenario = scenarioFor(decision);
    if (scenario) body.scenario_id = scenario;
    if (withResult) {
      const local: Record<string, string> = {};
      if (!recovered && !revenue) local.actual_recovered_kg = t("common.required");
      if (recovered && !(Number(recovered) >= 0)) local.actual_recovered_kg = t("err.greater_than_equal", { limit: 0 });
      if (revenue && !(Number(revenue) >= 0)) local.actual_revenue_fcfa = t("err.greater_than_equal", { limit: 0 });
      if (Object.keys(local).length) {
        setErrors(local);
        return;
      }
      if (recovered) body.actual_recovered_kg = Number(recovered);
      if (revenue) body.actual_revenue_fcfa = Number(revenue);
    }
    try {
      await api<Outcome>(`/lots/${lot.id}/outcomes`, { method: "POST", body });
      setMessage(withResult ? t("reco.resultSaved") : t("reco.decisionSaved"));
      history.reload();
      ctx.reloadLot();
    } catch (err) {
      const e = toApiError(err);
      const mapped = fieldErrors(e.errors, td);
      if (Object.keys(mapped).length) setErrors(mapped);
      else setFailure(e);
    }
  };

  const submitDecision = (event: FormEvent) => {
    event.preventDefault();
    send(false);
  };
  const submitResult = (event: FormEvent) => {
    event.preventDefault();
    send(true);
  };

  const actions: (Action | "other")[] = ["continue", "store", "reroute", "sell_local", "optimized_split", "other"];

  return (
    <section className="panel" aria-labelledby="decision-title">
      <h2 id="decision-title">{t("reco.decisionTitle")}</h2>
      <p className="muted">{t("reco.decisionIntro")}</p>
      {message && <Notice tone="ok">{message}</Notice>}
      {failure && <ErrorState error={failure} />}
      {outcomes.length > 0 && (
        <ul className="outcomes">
          {outcomes.map((o) => (
            <li key={o.id}>
              <strong>{t(`action.${o.decision_taken}`)}</strong>
              {o.followed_reco !== null && <span className="muted"> — {o.followed_reco ? t("reco.followed") : t("reco.notFollowed")}</span>}
              {(o.actual_recovered_kg !== null || o.actual_revenue_fcfa !== null) && (
                <span>
                  {" — "}
                  {kg(o.actual_recovered_kg, lang)}, {fcfa(o.actual_revenue_fcfa, lang)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {lot.status !== "closed" && (
        <>
          {lot.status === "open" && (
            <form className="inline-form" onSubmit={submitDecision}>
              <Field label={t("reco.decisionTaken")}>
                {(p) => (
                  <Select {...p} value={decision} onChange={(e) => setDecision(e.target.value as Action | "other")}>
                    {actions.map((a) => (
                      <option key={a} value={a}>
                        {t(`action.${a}`)}
                        {a === reco?.best_action ? ` (${t("sim.recommended").toLowerCase()})` : ""}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <button type="submit" className="button button--primary">{t("reco.decisionSave")}</button>
            </form>
          )}
          <form className="result-form" onSubmit={submitResult} noValidate>
            <h3>{t("reco.resultTitle")}</h3>
            {lot.status === "decided" && (
              <Field label={t("reco.decisionTaken")}>
                {(p) => (
                  <Select {...p} value={decision} onChange={(e) => setDecision(e.target.value as Action | "other")}>
                    {actions.map((a) => (
                      <option key={a} value={a}>{t(`action.${a}`)}</option>
                    ))}
                  </Select>
                )}
              </Field>
            )}
            <div className="grid-2">
              <Field label={t("reco.resultKg")} error={errors.actual_recovered_kg}>
                {(p) => <Input {...p} type="number" min={0} inputMode="decimal" value={recovered} onChange={(e) => setRecovered(e.target.value)} />}
              </Field>
              <Field label={t("reco.resultRevenue")} error={errors.actual_revenue_fcfa}>
                {(p) => <Input {...p} type="number" min={0} inputMode="decimal" value={revenue} onChange={(e) => setRevenue(e.target.value)} />}
              </Field>
            </div>
            <button type="submit" className="button button--quiet">{t("reco.resultSave")}</button>
          </form>
        </>
      )}
    </section>
  );
}

export function RecommendationView({ ctx }: { ctx: LotContext }) {
  const { t, td, lang } = useI18n();
  const { simulation, lot } = ctx;
  if (!simulation) return <Notice>{t("reco.none")}</Notice>;
  const reco = simulation.recommendation;
  const best = simulation.scenarios.find((s) => s.id === reco.best_scenario_id) ?? null;
  const candidates = reco.candidate_scenario_ids
    .map((id) => simulation.scenarios.find((s) => s.id === id))
    .filter((s): s is NonNullable<typeof s> => Boolean(s));
  const leastBad = reco.rationale_codes.includes("ALL_OPTIONS_DISCOURAGED") && best !== null;
  const reasons = reco.rationale_codes.filter((c) => !["ALL_OPTIONS_DISCOURAGED", "HEAVY_LOSSES_LIKELY", "NO_CLEAR_WINNER"].includes(c));
  const asPlanned = simulation.scenarios.find((s) => s.action === "continue" && s.feasible) ?? null;
  const gain =
    best && asPlanned && best.id !== asPlanned.id && best.net_value_fcfa.p50 !== null && asPlanned.net_value_fcfa.p50 !== null
      ? best.net_value_fcfa.p50 - asPlanned.net_value_fcfa.p50
      : null;

  return (
    <div className="recommendation">
      {best && !reco.no_clear_winner && (
        <section className={`banner banner--${reco.confidence}`} aria-labelledby="reco-title">
          <p className="banner__kicker">{t("reco.title")}</p>
          <h2 id="reco-title" className="banner__title">{best.label[lang]}</h2>
          <p className="banner__value">
            {t("sim.net", { value: fcfa(best.net_value_fcfa.p50, lang) })} —{" "}
            {t("sim.range", { p10: fcfa(best.net_value_fcfa.p10, lang), p90: fcfa(best.net_value_fcfa.p90, lang) })}
          </p>
          <p>
            {t("reco.confidence", {
              level: t(`reco.confidence.${reco.confidence}`),
              p: pct(reco.prob_best, lang),
            })}
          </p>
          {gain !== null && gain > 0 && (
            <p className="banner__impact">{t("reco.vsContinue", { market: lot.destination_name, diff: fcfa(gain, lang) })}</p>
          )}
          {asPlanned && best.id === asPlanned.id && <p className="banner__impact">{t("reco.vsContinueSame")}</p>}
          {best.action === "optimized_split" && <AllocationBar scenario={best} total={lot.quantity_kg} lang={lang} />}
          {leastBad && <Notice tone="warn">{t("reco.leastBad")}</Notice>}
          {reco.low_risk && <Notice tone="ok">{t("analysis.lowRisk")}</Notice>}
          {reasons.length > 0 && (
            <p className="banner__reasons">
              {t("reco.reasons")}{lang === "fr" ? " : " : ": "}{reasons.map((c) => td(`rationale.${c}`, c)).join(", ")}
            </p>
          )}
        </section>
      )}
      {reco.no_clear_winner && candidates.length >= 2 && (
        <section className="banner banner--none" aria-labelledby="reco-title">
          <h2 id="reco-title" className="banner__title">{t("reco.noWinnerTitle")}</h2>
          <p>{t("reco.noWinnerText")}</p>
          <div className="scenario-grid scenario-grid--two">
            {candidates.map((s) => (
              <ScenarioCard key={s.id} scenario={s} recommended={false} lotKg={lot.quantity_kg} />
            ))}
          </div>
        </section>
      )}
      {!best && !(reco.no_clear_winner && candidates.length >= 2) && <Notice tone="warn">{t("reco.nothing")}</Notice>}
      <div className="row-actions">
        {lot.status !== "closed" && (
          <button type="button" className="button button--quiet" onClick={() => ctx.go("simulation")}>
            {t("reco.redo")}
          </button>
        )}
        <Link to="/assumptions" className="button button--quiet">
          {t("reco.seeAssumptions")}
        </Link>
      </div>
      <ExplanationPanel recommendationId={reco.id} />
      <AskPanel analysisId={simulation.analysis_id} simulationId={simulation.id} />
      <OutcomeForms ctx={ctx} />
    </div>
  );
}
