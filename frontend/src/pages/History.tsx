import { useState } from "react";

import { EmptyState, ErrorState, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { toApiError, useApi } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import type { Lot, LotList } from "../lib/types";
import { LotRow } from "./Dashboard";

/** Every lot of the organization, each opening on its follow-up tab (FR-14). */
export function History() {
  const { t } = useI18n();
  const [closedOnly, setClosedOnly] = useState(false);
  const list = useApi<LotList>(`/lots?limit=50${closedOnly ? "&status=closed" : ""}`);
  const [extra, setExtra] = useState<Lot[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [moreError, setMoreError] = useState<string | null>(null);

  const items = [...(list.data?.items ?? []), ...extra];
  const next = extra.length ? cursor : (list.data?.next_cursor ?? null);

  const loadMore = async () => {
    if (!next) return;
    try {
      const page = await api<LotList>(
        `/lots?limit=50&cursor=${encodeURIComponent(next)}${closedOnly ? "&status=closed" : ""}`,
      );
      setExtra((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor);
    } catch (err) {
      setMoreError(toApiError(err).message);
    }
  };

  return (
    <div className="page">
      <div className="page__head">
        <h1>{t("history.title")}</h1>
      </div>
      <p className="lede">{t("history.pageIntro")}</p>
      <label className="check">
        <input
          type="checkbox"
          checked={closedOnly}
          onChange={(e) => {
            setClosedOnly(e.target.checked);
            setExtra([]);
            setCursor(null);
          }}
        />
        {t("history.filterClosed")}
      </label>
      {list.loading && !list.data && <Skeleton lines={4} />}
      {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.data && items.length === 0 && <EmptyState title={t("history.noOutcome")} />}
      {items.length > 0 && (
        <ul className="lot-list">
          {items.map((lot) => (
            <LotRow key={lot.id} lot={lot} to={`/lots/${lot.id}/history`} />
          ))}
        </ul>
      )}
      {next && (
        <button type="button" className="button button--quiet" onClick={loadMore}>
          {t("dash.more")}
        </button>
      )}
      {moreError && <p className="field__error">{moreError}</p>}
    </div>
  );
}
