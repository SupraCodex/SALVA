import type { Lang, Scenario } from "../lib/types";
import { fcfa, kg, pct } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { AllocationBar } from "./charts";

export function ScenarioCard({
  scenario,
  recommended,
  lotKg,
}: {
  scenario: Scenario;
  recommended: boolean;
  lotKg: number;
}) {
  const { t, td, lang } = useI18n();
  const n = scenario.net_value_fcfa;
  const r = scenario.recoverable_kg;
  return (
    <article
      className={`scenario${recommended ? " scenario--best" : ""}${scenario.discouraged ? " scenario--discouraged" : ""}`}
      aria-label={scenario.label[lang]}
    >
      <header className="scenario__head">
        <span className="scenario__action">{t(`action.${scenario.action}`)}</span>
        {recommended && <span className="tag tag--best">{t("sim.recommended")}</span>}
      </header>
      <h3 className="scenario__label">{scenario.label[lang]}</h3>
      <p className="scenario__net">{t("sim.net", { value: fcfa(n.p50, lang) })}</p>
      <p className="scenario__range">{t("sim.range", { p10: fcfa(n.p10, lang), p90: fcfa(n.p90, lang) })}</p>
      <p className="scenario__kg" title={t("sim.kgEqHelp")}>
        {t("sim.kgEq", { kg: kg(r.p50, lang) })}
      </p>
      <p className="scenario__prob">{t("sim.probBest", { p: pct(scenario.prob_best, lang) })}</p>
      {scenario.action === "optimized_split" && <AllocationBar scenario={scenario} total={lotKg} lang={lang} />}
      {scenario.discouraged && <p className="scenario__warn">{td(`reason.${scenario.discouraged_reason}`, t("sim.discouraged"))}</p>}
    </article>
  );
}

export function UnavailableList({ scenarios, lang }: { scenarios: Scenario[]; lang: Lang }) {
  const { t, td } = useI18n();
  if (!scenarios.length) return null;
  return (
    <ul className="unavailable">
      {scenarios.map((s) => (
        <li key={s.id}>
          <strong>{s.label[lang]}</strong> — {t("sim.infeasible")}{lang === "fr" ? " : " : ": "}{td(`reason.${s.infeasible_reason}`, s.infeasible_reason ?? "")}
        </li>
      ))}
    </ul>
  );
}

/** Feasible scenarios ordered by the recommendation ranking, then the others. */
export function orderScenarios(scenarios: Scenario[], ranked: string[]): Scenario[] {
  const index = new Map(ranked.map((id, i) => [id, i]));
  return scenarios
    .filter((s) => s.feasible)
    .sort((a, b) => (index.get(a.id) ?? 99) - (index.get(b.id) ?? 99) || (b.net_value_fcfa.p50 ?? 0) - (a.net_value_fcfa.p50 ?? 0));
}
