import { useState } from "react";

import { RiskIcon } from "../components/charts";
import { EmptyState, ErrorState, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, hours, kg, pct } from "../lib/format";
import { useApi, toApiError } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { Link } from "../lib/router";
import type { Lot, LotList } from "../lib/types";

type Filter = "" | "open" | "decided" | "closed";

export function LotRow({ lot, to }: { lot: Lot; to?: string }) {
  const { t, lang } = useI18n();
  const a = lot.latest_analysis;
  return (
    <li className="lot-row">
      <Link to={to ?? `/lots/${lot.id}`} className="lot-row__link">
        <span className="lot-row__main">
          <span className="lot-row__title">
            {t(`lot.product.${lot.product_code}` as "lot.product.tomato")} · {kg(lot.quantity_kg, lang)}
          </span>
          <span className="lot-row__route">{t("lot.route", { from: lot.origin_label, to: `${lot.destination_name} (${lot.destination_city})` })}</span>
          <span className="lot-row__meta muted small">
            {t("hub.arrival", { date: dateTime(lot.eta_current_at, lang) })}
            {lot.delay_h > 0 ? ` — ${t("lot.delay", { h: hours(lot.delay_h, lang) })}` : ""}
          </span>
        </span>
        <span className="lot-row__side">
          {a ? (
            <>
              <span className={`risk-pill risk-pill--${a.risk_level}`}>
                <RiskIcon level={a.risk_level} /> {t(`analysis.level.${a.risk_level}`)} · {pct(a.loss_p50, lang)}
              </span>
              <span className="small">
                {a.no_clear_winner
                  ? t("dash.noWinner")
                  : a.recommended_action
                    ? t("dash.recommended", { action: t(`action.${a.recommended_action}`) })
                    : ""}
              </span>
            </>
          ) : (
            <span className="muted small">{t("dash.notAnalysed")}</span>
          )}
          <span className={`status status--${lot.status}`}>{t(`lot.status.${lot.status}`)}</span>
        </span>
      </Link>
    </li>
  );
}

export function Dashboard() {
  const { t } = useI18n();
  const [filter, setFilter] = useState<Filter>("");
  const list = useApi<LotList>(`/lots?limit=20${filter ? `&status=${filter}` : ""}`);
  const [extra, setExtra] = useState<Lot[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [moreError, setMoreError] = useState<string | null>(null);

  const items = [...(list.data?.items ?? []), ...extra];
  const next = extra.length ? cursor : (list.data?.next_cursor ?? null);
  const atRisk = items.filter((l) => l.status === "open" && l.latest_analysis?.risk_level === "high");

  const loadMore = async () => {
    if (!next) return;
    try {
      const page = await api<LotList>(`/lots?limit=20&cursor=${encodeURIComponent(next)}${filter ? `&status=${filter}` : ""}`);
      setExtra((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor);
    } catch (err) {
      setMoreError(toApiError(err).message);
    }
  };
  const changeFilter = (value: Filter) => {
    setFilter(value);
    setExtra([]);
    setCursor(null);
  };

  return (
    <div className="page">
      <div className="page__head">
        <h1>{t("dash.title")}</h1>
        <Link to="/lots/new" className="button button--primary">
          {t("dash.new")}
        </Link>
      </div>
      {list.loading && !list.data && <Skeleton lines={4} />}
      {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.data && items.length === 0 && !filter && (
        <EmptyState
          title={t("dash.emptyTitle")}
          action={
            <div className="row-actions row-actions--center">
              <Link to="/lots/new" className="button button--primary">
                {t("dash.emptyAction")}
              </Link>
              <Link to="/lots/new?example=1" className="button button--quiet">
                {t("dash.emptyExample")}
              </Link>
            </div>
          }
        >
          <p>{t("dash.emptyText")}</p>
        </EmptyState>
      )}
      {atRisk.length > 0 && !filter && (
        <section className="section">
          <h2>{t("dash.atRisk")}</h2>
          <ul className="lot-list">{atRisk.map((lot) => <LotRow key={lot.id} lot={lot} />)}</ul>
        </section>
      )}
      {(items.length > 0 || filter) && (
        <section className="section">
          <div className="section__head">
            <h2>{t("dash.all")}</h2>
            <div className="chips" role="group" aria-label={t("dash.all")}>
              {(["", "open", "decided", "closed"] as Filter[]).map((value) => (
                <button
                  key={value || "all"}
                  type="button"
                  className={`chip${filter === value ? " is-active" : ""}`}
                  aria-pressed={filter === value}
                  onClick={() => changeFilter(value)}
                >
                  {t(value ? (`dash.filter${value[0].toUpperCase()}${value.slice(1)}` as "dash.filterOpen") : "dash.filterAll")}
                </button>
              ))}
            </div>
          </div>
          <ul className="lot-list">{items.map((lot) => <LotRow key={lot.id} lot={lot} />)}</ul>
          {next && (
            <button type="button" className="button button--quiet" onClick={loadMore}>
              {t("dash.more")}
            </button>
          )}
          {moreError && <p className="field__error">{moreError}</p>}
        </section>
      )}
    </div>
  );
}
