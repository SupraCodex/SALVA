import { useMemo, useState } from "react";

import { ComparisonChart } from "../../components/charts";
import { orderScenarios, ScenarioCard, UnavailableList } from "../../components/scenarios";
import { ErrorState, Field, Input, Notice, Segmented, SourceBadge, Spinner } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { fcfa, hours, kg, num } from "../../lib/format";
import { toApiError, useApi } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";
import type { Assumption, Market, RiskProfile, Sensitivity, Simulation, SimulationRequest } from "../../lib/types";
import type { LotContext } from "../LotHub";

interface Draft {
  profile: RiskProfile;
  markets: Record<string, { price: string; absorption: string }>;
  hold: string;
  transport: string;
  surplus: string;
}

function draftFrom(sim: Simulation | null, markets: Market[]): Draft {
  const byKey = new Map((sim?.assumptions ?? []).map((a) => [a.key, a]));
  const draft: Draft = { profile: sim?.risk_profile ?? "balanced", markets: {}, hold: "", transport: "", surplus: "" };
  for (const m of markets) {
    const price = byKey.get(`price_fcfa_kg:${m.code}`);
    const absorption = byKey.get(`absorption_kg:${m.code}`);
    if (price || absorption) {
      draft.markets[m.id] = {
        price: price?.user_override ? String(price.value) : "",
        absorption: absorption?.user_override ? String(absorption.value) : "",
      };
    }
  }
  const pick = (key: string) => (byKey.get(key)?.user_override ? String(byKey.get(key)?.value) : "");
  draft.hold = pick("hold_h");
  draft.transport = pick("transport_fcfa_kg_km");
  draft.surplus = pick("surplus_price_fraction");
  return draft;
}

function requestFrom(draft: Draft): SimulationRequest {
  const req: SimulationRequest = { risk_profile: draft.profile, assumptions: { markets: {} } };
  for (const [id, v] of Object.entries(draft.markets)) {
    const o: { price_fcfa_kg?: number; absorption_kg?: number } = {};
    if (v.price) o.price_fcfa_kg = Number(v.price);
    if (v.absorption) o.absorption_kg = Number(v.absorption);
    if (Object.keys(o).length) req.assumptions.markets[id] = o;
  }
  if (draft.hold) req.assumptions.hold_h = Number(draft.hold);
  if (draft.transport) req.assumptions.transport_fcfa_kg_km = Number(draft.transport);
  if (draft.surplus) req.assumptions.surplus_price_fraction = Number(draft.surplus);
  return req;
}

function assumptionLabel(a: Assumption, markets: Market[], simulation: Simulation, td: (k: string, f?: string) => string, lang: "fr" | "en"): string {
  const [kind, ...rest] = a.key.split(":");
  const ref = rest.join(":");
  let x = ref;
  if (kind === "price_fcfa_kg" || kind === "absorption_kg") {
    const m = markets.find((mk) => mk.code === ref);
    x = m ? `${m.name} (${m.city})` : ref;
  } else if (kind === "route_km") {
    const sc = simulation.scenarios.find((s) => s.key === ref);
    x = sc ? sc.label[lang] : ref;
  }
  return td(`assume.${kind}`, a.key).replace("{x}", x);
}

function AssumptionValue({ a }: { a: Assumption }) {
  const { lang, t } = useI18n();
  if (a.key === "position") return <>{t("assume.positionValue")}</>;
  if (typeof a.value === "number") {
    if (a.unit === "FCFA/kg") return <>{fcfa(a.value, lang)}/kg</>;
    if (a.unit === "kg") return <>{kg(a.value, lang)}</>;
    if (a.unit === "h") return <>{hours(a.value, lang)}</>;
    return <>{num(a.value, lang, 2)} {a.unit}</>;
  }
  return <>{a.value}</>;
}

function SensitivityPanel({ simulation }: { simulation: Simulation }) {
  const { t, lang } = useI18n();
  const [data, setData] = useState<Sensitivity | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setData(await api<Sensitivity>(`/simulations/${simulation.id}/sensitivity`, { method: "POST", body: {} }));
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  };
  const actionName = (a: string | null) => (a ? t(`action.${a}` as "action.continue") : t("action.none"));
  return (
    <section className="panel" aria-labelledby="sens-title">
      <h2 id="sens-title">{t("sim.sensitivityTitle")}</h2>
      {!data && !busy && (
        <button type="button" className="button button--quiet" onClick={run}>
          {t("sim.sensitivityRun")}
        </button>
      )}
      {busy && <Spinner label={t("sim.sensitivityRunning")} />}
      {error && <ErrorState error={error} onRetry={run} />}
      {data && (
        <>
          <div className="sens-grid" role="table" aria-label={t("sim.sensitivityTitle")} style={{ ["--cols" as string]: data.delays_h.length }}>
            <div role="row" className="sens-grid__row sens-grid__row--head">
              <span role="columnheader" className="sens-grid__corner">
                {t("sim.sensitivityAxisT")} \ {t("sim.sensitivityAxisD")}
              </span>
              {data.delays_h.map((d) => (
                <span role="columnheader" key={d}>{hours(d, lang)}</span>
              ))}
            </div>
            {data.temperatures_c.map((temp) => (
              <div role="row" className="sens-grid__row" key={temp}>
                <span role="rowheader">{num(temp, lang)} °C</span>
                {data.delays_h.map((d) => {
                  const pt = data.points.find((p) => p.temp_c === temp && p.delay_h === d);
                  const current = Math.abs(temp - data.current.temp_c) < 0.05 && Math.abs(d - data.current.delay_h) < 0.05;
                  return (
                    <span role="cell" key={d} className={`sens-cell sens-cell--${pt?.best_action ?? "none"}${current ? " is-current" : ""}`}
                      title={current ? t("sim.sensitivityCurrent") : undefined}>
                      {actionName(pt?.best_action ?? null)}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
          {data.transitions.length === 0 ? (
            <p>{t("sim.sensitivityNone")}</p>
          ) : (
            <ul className="transitions">
              {data.transitions.slice(0, 6).map((tr, i) => {
                const unit = tr.axis === "temperature" ? " °C" : " h";
                const other = tr.axis === "temperature" ? `${hours(tr.fixed_value, lang)}` : `${num(tr.fixed_value, lang)} °C`;
                return (
                  <li key={i}>
                    {t("sim.sensitivityTransition", {
                      axis: tr.axis === "temperature" ? t("sim.sensitivityAxisT") : t("sim.sensitivityAxisD"),
                      from: `${num(tr.from_value, lang)}${unit}`,
                      to: `${num(tr.to_value, lang)}${unit}`,
                      fixed: other,
                      a: actionName(tr.from_action),
                      b: actionName(tr.to_action),
                    })}
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

export function SimulationView({ ctx }: { ctx: LotContext }) {
  const { t, td, lang } = useI18n();
  const { lot, analysis, simulation } = ctx;
  const markets = useApi<Market[]>("/markets");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);

  const currentDraft = useMemo(() => draft ?? draftFrom(simulation, markets.data ?? []), [draft, simulation, markets.data]);
  const involved = useMemo(() => {
    const codes = new Set((simulation?.assumptions ?? []).filter((a) => a.key.startsWith("price_fcfa_kg:")).map((a) => a.key.split(":")[1]));
    return (markets.data ?? []).filter((m) => codes.has(m.code) || m.id === lot.destination_market_id);
  }, [simulation, markets.data, lot.destination_market_id]);

  if (!analysis) {
    return <Notice>{t("analysis.none")}</Notice>;
  }

  const run = async (request: SimulationRequest) => {
    setBusy(true);
    setError(null);
    try {
      const result = await api<Simulation>(`/analyses/${analysis.id}/simulations`, { method: "POST", body: request });
      ctx.setSimulation(result);
      setDraft(null);
      setEditing(false);
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const update = (patch: Partial<Draft>) => setDraft({ ...currentDraft, ...patch });
  const updateMarket = (id: string, key: "price" | "absorption", value: string) =>
    setDraft({ ...currentDraft, markets: { ...currentDraft.markets, [id]: { ...(currentDraft.markets[id] ?? { price: "", absorption: "" }), [key]: value } } });

  const profilePicker = (
    <Segmented
      legend={t("sim.profile")}
      name="risk_profile"
      value={currentDraft.profile}
      onChange={(v) => update({ profile: v })}
      help={t("sim.profileHelp")}
      options={(["prudent", "balanced", "ambitious"] as RiskProfile[]).map((p) => ({ value: p, label: t(`sim.profile.${p}`) }))}
    />
  );

  const editor = editing && (
    <section className="panel drawer" aria-labelledby="assumptions-edit">
      <div className="panel__head">
        <h2 id="assumptions-edit">{t("sim.editAssumptions")}</h2>
        <button type="button" className="button button--quiet button--small" onClick={() => setEditing(false)}>
          {t("sim.closeAssumptions")}
        </button>
      </div>
      {profilePicker}
      {involved.map((m) => (
        <div className="grid-2" key={m.id}>
          <Field label={t("sim.marketPrice", { market: m.name })} hint={`${t("assumptions.reference")}${lang === "fr" ? " : " : ": "}${fcfa(m.ref_price_fcfa_kg, lang)}`} optional>
            {(p) => (
              <Input {...p} type="number" min={1} value={currentDraft.markets[m.id]?.price ?? ""} placeholder={String(m.ref_price_fcfa_kg)}
                onChange={(e) => updateMarket(m.id, "price", e.target.value)} />
            )}
          </Field>
          <Field label={t("sim.marketAbsorption", { market: m.name })} hint={t("sim.absorptionHelp")} optional>
            {(p) => (
              <Input {...p} type="number" min={0} value={currentDraft.markets[m.id]?.absorption ?? ""} placeholder={String(m.absorption_kg_day)}
                onChange={(e) => updateMarket(m.id, "absorption", e.target.value)} />
            )}
          </Field>
        </div>
      ))}
      <div className="grid-3">
        <Field label={t("sim.holdH")} optional>
          {(p) => <Input {...p} type="number" min={1} max={72} value={currentDraft.hold} placeholder="24" onChange={(e) => update({ hold: e.target.value })} />}
        </Field>
        <Field label={t("sim.transport")} optional>
          {(p) => <Input {...p} type="number" min={0} max={10} step="0.01" value={currentDraft.transport} placeholder="0.1" onChange={(e) => update({ transport: e.target.value })} />}
        </Field>
        <Field label={t("sim.surplus")} optional>
          {(p) => <Input {...p} type="number" min={0} max={1} step="0.05" value={currentDraft.surplus} placeholder="0.5" onChange={(e) => update({ surplus: e.target.value })} />}
        </Field>
      </div>
      <div className="row-actions">
        <button type="button" className="button button--primary" disabled={busy} onClick={() => run(requestFrom(currentDraft))}>
          {t("sim.rerun")}
        </button>
        <button type="button" className="button button--quiet" disabled={busy}
          onClick={() => run({ risk_profile: currentDraft.profile, assumptions: { markets: {} } })}>
          {t("sim.reset")}
        </button>
      </div>
    </section>
  );

  if (busy) return <Spinner label={t("sim.running", { n: simulation?.n_draws ?? 2000 })} />;

  if (!simulation) {
    return (
      <section className="panel">
        <h2>{t("sim.title")}</h2>
        <p>{t("sim.none")}</p>
        {error && <ErrorState error={error} />}
        {lot.status !== "closed" && (
          <>
            {profilePicker}
            <button type="button" className="button button--primary" onClick={() => run(requestFrom(currentDraft))}>
              {t("sim.run")}
            </button>
          </>
        )}
      </section>
    );
  }

  const reco = simulation.recommendation;
  const feasible = orderScenarios(simulation.scenarios, reco.ranked_scenario_ids);
  const unavailable = simulation.scenarios.filter((s) => !s.feasible);
  const hasSplit = feasible.some((s) => s.action === "optimized_split");

  return (
    <div className="simulation">
      {error && <ErrorState error={error} />}
      <div className="page__head">
        <h2>{t("sim.title")}</h2>
        {lot.status !== "closed" && (
          <button type="button" className="button button--quiet" onClick={() => setEditing((v) => !v)} aria-expanded={editing}>
            {t("sim.editAssumptions")}
          </button>
        )}
      </div>
      {editor}
      <div className="scenario-grid">
        {feasible.map((s) => (
          <ScenarioCard key={s.id} scenario={s} recommended={s.id === reco.best_scenario_id} lotKg={lot.quantity_kg} />
        ))}
      </div>
      {!hasSplit && feasible.length >= 2 && <p className="muted">{t("sim.splitIdentical")}</p>}
      <UnavailableList scenarios={unavailable} lang={lang} />
      <section className="panel">
        <ComparisonChart scenarios={feasible} bestId={reco.best_scenario_id} />
      </section>
      <section className="panel" aria-labelledby="assumptions-list">
        <h2 id="assumptions-list">{t("sim.assumptionsTitle")}</h2>
        <ul className="assumption-list">
          {simulation.assumptions.map((a) => (
            <li key={a.key}>
              <span className="assumption-list__key">{assumptionLabel(a, markets.data ?? [], simulation, td, lang)}</span>
              <span>
                <AssumptionValue a={a} /> {a.user_override ? <span className="badge badge--manual">{t("sim.overrideBadge")}</span> : <SourceBadge source={a.source} />}
              </span>
            </li>
          ))}
        </ul>
        <p className="muted small">
          {t("sim.duration", { n: simulation.n_draws, seed: simulation.seed, ms: Math.round(simulation.duration_ms) })}
        </p>
      </section>
      <SensitivityPanel simulation={simulation} />
      <div className="next-step">
        <button type="button" className="button button--primary" onClick={() => ctx.go("recommendation")}>
          {t("sim.goReco")}
        </button>
      </div>
    </div>
  );
}
