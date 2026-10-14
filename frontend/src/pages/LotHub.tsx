import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ErrorState, Field, Input, Notice, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, fromLocalInput, hours, kg, toLocalInput } from "../lib/format";
import { toApiError, useApi } from "../lib/hooks";
import { fieldErrors, useI18n } from "../lib/i18n";
import { Link, useRouter } from "../lib/router";
import type { Analysis, Lot, Simulation } from "../lib/types";
import { AnalysisView } from "./lot/AnalysisView";
import { HistoryView } from "./lot/HistoryView";
import { RecommendationView } from "./lot/RecommendationView";
import { SimulationView } from "./lot/SimulationView";

export type Tab = "analysis" | "simulation" | "recommendation" | "history";

export interface LotContext {
  lot: Lot;
  analysis: Analysis | null;
  simulation: Simulation | null;
  setAnalysis: (a: Analysis) => void;
  setSimulation: (s: Simulation) => void;
  reloadLot: () => void;
  go: (tab: Tab) => void;
}

function EditLot({ lot, onSaved }: { lot: Lot; onSaved: () => void }) {
  const { t, td } = useI18n();
  const [open, setOpen] = useState(false);
  const [eta, setEta] = useState(toLocalInput(lot.eta_current_at));
  const [temp, setTemp] = useState(lot.temp_override_c?.toString() ?? "");
  const [price, setPrice] = useState(lot.price_override_fcfa_kg?.toString() ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  if (lot.status === "closed") return null;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await api(`/lots/${lot.id}`, {
        method: "PATCH",
        body: {
          eta_current_at: fromLocalInput(eta),
          temp_override_c: temp ? Number(temp) : null,
          price_override_fcfa_kg: price ? Number(price) : null,
        },
      });
      setErrors({});
      setSaved(true);
      setOpen(false);
      onSaved();
    } catch (err) {
      const e = toApiError(err);
      setErrors(Object.keys(fieldErrors(e.errors, td)).length ? fieldErrors(e.errors, td) : { _: e.message });
    }
  };
  return (
    <div className="edit-lot">
      {saved && !open && <Notice tone="ok">{t("hub.saved")}</Notice>}
      {!open ? (
        <button type="button" className="link-button" onClick={() => { setOpen(true); setSaved(false); }}>
          {t("hub.edit")}
        </button>
      ) : (
        <form className="edit-lot__form" onSubmit={submit} noValidate>
          {errors._ && <Notice tone="error">{errors._}</Notice>}
          <div className="grid-3">
            <Field label={t("form.eta")} error={errors.eta_current_at}>
              {(p) => <Input {...p} type="datetime-local" value={eta} onChange={(e) => setEta(e.target.value)} />}
            </Field>
            <Field label={t("form.temp")} error={errors.temp_override_c} optional>
              {(p) => <Input {...p} type="number" min={0} max={50} step="0.1" value={temp} onChange={(e) => setTemp(e.target.value)} />}
            </Field>
            <Field label={t("form.price")} error={errors.price_override_fcfa_kg} optional>
              {(p) => <Input {...p} type="number" min={1} value={price} onChange={(e) => setPrice(e.target.value)} />}
            </Field>
          </div>
          <div className="row-actions">
            <button type="submit" className="button button--primary">{t("hub.save")}</button>
            <button type="button" className="button button--quiet" onClick={() => setOpen(false)}>{t("hub.cancel")}</button>
          </div>
        </form>
      )}
    </div>
  );
}

export function LotHub({ id, tab }: { id: string; tab: Tab }) {
  const { t, lang } = useI18n();
  const { navigate } = useRouter();
  const lotState = useApi<Lot>(`/lots/${id}`);
  const lot = lotState.data;
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [loadingResults, setLoadingResults] = useState(true);

  const latestAnalysisId = lot?.latest_analysis?.id ?? null;
  const latestSimulationId = lot?.latest_analysis?.simulation_id ?? null;

  useEffect(() => {
    if (!lot) return;
    let cancelled = false;
    setLoadingResults(true);
    (async () => {
      try {
        const a = latestAnalysisId ? await api<Analysis>(`/analyses/${latestAnalysisId}`) : null;
        const s = latestSimulationId ? await api<Simulation>(`/simulations/${latestSimulationId}`) : null;
        if (!cancelled) {
          setAnalysis(a);
          setSimulation(s);
        }
      } finally {
        if (!cancelled) setLoadingResults(false);
      }
    })().catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // Reload results only when the latest identifiers change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestAnalysisId, latestSimulationId, lot === null]);

  const go = useCallback((next: Tab) => navigate(`/lots/${id}/${next}`), [id, navigate]);

  if (lotState.error) {
    return (
      <div className="page">
        <ErrorState error={lotState.error} onRetry={lotState.reload} />
      </div>
    );
  }
  if (!lot) {
    return (
      <div className="page">
        <Skeleton lines={5} />
      </div>
    );
  }

  const ctx: LotContext = {
    lot,
    analysis,
    simulation,
    setAnalysis: (a) => {
      setAnalysis(a);
      setSimulation(null);
      lotState.reload();
    },
    setSimulation: (s) => {
      setSimulation(s);
      lotState.reload();
    },
    reloadLot: lotState.reload,
    go,
  };

  const steps: { tab: Tab; label: string; enabled: boolean }[] = [
    { tab: "analysis", label: t("steps.analysis"), enabled: true },
    { tab: "simulation", label: t("steps.simulation"), enabled: analysis !== null },
    { tab: "recommendation", label: t("steps.recommendation"), enabled: simulation !== null },
    { tab: "history", label: t("steps.history"), enabled: true },
  ];

  return (
    <div className="page">
      <Link to="/" className="back-link">{t("hub.back")}</Link>
      <header className="lot-head">
        <div>
          <h1 className="lot-head__title">
            {t(`lot.product.${lot.product_code}` as "lot.product.tomato")} · {kg(lot.quantity_kg, lang)}
          </h1>
          <p className="lot-head__route">
            {t("lot.route", { from: lot.origin_label, to: `${lot.destination_name} (${lot.destination_city})` })}
          </p>
          <p className="muted small">
            {t("hub.harvest", { date: dateTime(lot.harvested_at, lang) })} — {t(`lot.maturity.${lot.maturity}`)},{" "}
            {t(`lot.packaging.${lot.packaging}`).toLowerCase()} — {t("hub.arrival", { date: dateTime(lot.eta_current_at, lang) })}
            {lot.delay_h > 0 ? ` (${t("lot.delay", { h: hours(lot.delay_h, lang) })})` : ""}
          </p>
        </div>
        <span className={`status status--${lot.status}`}>{t(`lot.status.${lot.status}`)}</span>
      </header>
      <EditLot lot={lot} onSaved={lotState.reload} />
      {lot.status === "closed" && <Notice>{t("hub.closed")}</Notice>}

      <nav className="steps" aria-label={t("steps.analysis")}>
        <ol>
          {steps.map((s, i) => (
            <li key={s.tab}>
              {s.enabled ? (
                <Link
                  to={`/lots/${lot.id}/${s.tab}`}
                  className={`steps__item${tab === s.tab ? " is-active" : ""}`}
                  aria-current={tab === s.tab ? "step" : undefined}
                >
                  <span className="steps__num" aria-hidden="true">{i < 3 ? i + 1 : ""}</span>
                  {s.label}
                </Link>
              ) : (
                <span className="steps__item is-disabled" aria-disabled="true">
                  <span className="steps__num" aria-hidden="true">{i + 1}</span>
                  {s.label}
                </span>
              )}
            </li>
          ))}
        </ol>
      </nav>

      {loadingResults && tab !== "history" ? (
        <Skeleton lines={5} />
      ) : (
        <>
          {tab === "analysis" && <AnalysisView ctx={ctx} />}
          {tab === "simulation" && <SimulationView ctx={ctx} />}
          {tab === "recommendation" && <RecommendationView ctx={ctx} />}
          {tab === "history" && <HistoryView ctx={ctx} />}
        </>
      )}
    </div>
  );
}

