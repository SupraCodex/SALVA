// Uncertainty is always drawn as a band (P10–P90) with a central tick (P50), never a lone number.

import type { Action, Factor, Lang, RiskLevel, Scenario } from "../lib/types";
import { fcfa, kg, pct } from "../lib/format";
import { useI18n } from "../lib/i18n";

const RISK_BANDS = [
  { level: "low" as RiskLevel, to: 0.1 },
  { level: "medium" as RiskLevel, to: 0.25 },
  { level: "high" as RiskLevel, to: 1 },
];

/** Loss-of-value gauge on the ripening scale green → amber → red, with the likely range. */
export function RiskGauge({ p10, p50, p90, level }: { p10: number; p50: number; p90: number; level: RiskLevel }) {
  const { t, lang } = useI18n();
  let start = 0;
  return (
    <figure className="gauge">
      <div
        className="gauge__track"
        role="img"
        aria-label={t("analysis.lossRange", { p10: pct(p10, lang), p50: pct(p50, lang), p90: pct(p90, lang) })}
      >
        {RISK_BANDS.map((band) => {
          const seg = (
            <span
              key={band.level}
              className={`gauge__zone gauge__zone--${band.level}`}
              style={{ left: `${start * 100}%`, width: `${(band.to - start) * 100}%` }}
            />
          );
          start = band.to;
          return seg;
        })}
        <span className="gauge__band" style={{ left: `${p10 * 100}%`, width: `${Math.max(0.6, (p90 - p10) * 100)}%` }} />
        <span className="gauge__tick" style={{ left: `${p50 * 100}%` }} />
      </div>
      <div className="gauge__scale" aria-hidden="true">
        <span>0 %</span>
        <span>50 %</span>
        <span>100 %</span>
      </div>
      <figcaption className="gauge__caption">
        <span className={`risk-pill risk-pill--${level}`}>
          <RiskIcon level={level} /> {t(`analysis.level.${level}`)}
        </span>
        <span>{t("analysis.lossRange", { p10: pct(p10, lang), p50: pct(p50, lang), p90: pct(p90, lang) })}</span>
      </figcaption>
    </figure>
  );
}

/** Shape differs per level so colour is never the only signal (NFR-10). */
export function RiskIcon({ level }: { level: RiskLevel }) {
  if (level === "low")
    return (
      <svg viewBox="0 0 12 12" className="risk-icon" aria-hidden="true">
        <circle cx="6" cy="6" r="5" />
      </svg>
    );
  if (level === "medium")
    return (
      <svg viewBox="0 0 12 12" className="risk-icon" aria-hidden="true">
        <path d="M6 1 11 11H1Z" />
      </svg>
    );
  return (
    <svg viewBox="0 0 12 12" className="risk-icon" aria-hidden="true">
      <path d="M4 1h4l3 3v4l-3 3H4L1 8V4Z" />
    </svg>
  );
}

export function FactorList({ factors }: { factors: Factor[] }) {
  const { td, lang } = useI18n();
  const shown = factors.slice(0, 4);
  const max = Math.max(...shown.map((f) => Math.abs(f.contribution)), 0.01);
  return (
    <ul className="factors">
      {shown.map((f) => (
        <li key={f.name} className={`factor factor--${f.direction}`}>
          <span className="factor__name">{td(`factor.${f.name}`, f.name)}</span>
          <span className="factor__bar" aria-hidden="true">
            <span style={{ width: `${(Math.abs(f.contribution) / max) * 100}%` }} />
          </span>
          <span className="factor__value">
            {f.contribution >= 0 ? "+" : "−"}
            {pct(Math.abs(f.contribution), lang)}
          </span>
        </li>
      ))}
    </ul>
  );
}

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const mag = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 2.5, 5, 10]) if (step * mag >= value) return step * mag;
  return 10 * mag;
}

/** Horizontal intervals of net value for each feasible scenario on one shared scale. */
export function ComparisonChart({ scenarios, bestId }: { scenarios: Scenario[]; bestId: string | null }) {
  const { t, lang } = useI18n();
  const rows = scenarios.filter((s) => s.feasible && s.net_value_fcfa.p50 !== null);
  if (!rows.length) return null;
  const lo = Math.min(0, ...rows.map((s) => s.net_value_fcfa.p10 ?? 0));
  const hi = niceMax(Math.max(...rows.map((s) => s.net_value_fcfa.p90 ?? 0)));
  const x = (v: number) => ((v - lo) / (hi - lo)) * 100;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => lo + f * (hi - lo));
  return (
    <figure className="chart">
      <figcaption className="chart__title">{t("sim.chartTitle")}</figcaption>
      <div className="chart__rows">
        {rows.map((s) => {
          const n = s.net_value_fcfa;
          return (
            <div key={s.id} className={`chart__row${s.id === bestId ? " is-best" : ""}${s.discouraged ? " is-discouraged" : ""}`}>
              <span className="chart__label">{s.label[lang]}</span>
              <span
                className="chart__track"
                role="img"
                aria-label={`${s.label[lang]} : ${t("sim.range", { p10: fcfa(n.p10, lang), p90: fcfa(n.p90, lang) })}`}
              >
                <span className="chart__band" style={{ left: `${x(n.p10 ?? 0)}%`, width: `${Math.max(0.8, x(n.p90 ?? 0) - x(n.p10 ?? 0))}%` }} />
                <span className="chart__tick" style={{ left: `${x(n.p50 ?? 0)}%` }} />
              </span>
              <span className="chart__value">{fcfa(n.p50, lang)}</span>
            </div>
          );
        })}
      </div>
      <div className="chart__axis" aria-hidden="true">
        {ticks.map((v) => (
          <span key={v} style={{ left: `${x(v)}%` }}>
            {new Intl.NumberFormat(lang === "fr" ? "fr-FR" : "en-GB", { notation: "compact", maximumFractionDigits: 1 }).format(v)}
          </span>
        ))}
      </div>
    </figure>
  );
}

const ACTION_TONE: Record<Action, string> = {
  continue: "a",
  store: "b",
  reroute: "c",
  sell_local: "d",
  optimized_split: "e",
};

export function AllocationBar({ scenario, total, lang }: { scenario: Scenario; total: number; lang: Lang }) {
  const { t } = useI18n();
  const parts = [...scenario.allocation];
  return (
    <div className="allocation">
      <div className="allocation__bar" role="img" aria-label={parts.map((p) => `${p.label[lang]} ${kg(p.kg, lang)}`).join(", ")}>
        {parts.map((p) => (
          <span key={p.scenario_key} className={`allocation__part tone-${ACTION_TONE[p.action]}`} style={{ width: `${(p.kg / total) * 100}%` }} />
        ))}
        {scenario.discarded_kg > 0.5 && (
          <span className="allocation__part tone-x" style={{ width: `${(scenario.discarded_kg / total) * 100}%` }} />
        )}
      </div>
      <ul className="allocation__legend">
        {parts.map((p) => (
          <li key={p.scenario_key}>
            <span className={`swatch tone-${ACTION_TONE[p.action]}`} aria-hidden="true" />
            {kg(p.kg, lang)} · {p.label[lang]}
          </li>
        ))}
        {scenario.discarded_kg > 0.5 && (
          <li>
            <span className="swatch tone-x" aria-hidden="true" />
            {t("sim.discarded", { kg: kg(scenario.discarded_kg, lang) })}
          </li>
        )}
      </ul>
    </div>
  );
}
