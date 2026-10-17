import { ErrorState, Notice, Skeleton } from "../components/ui";
import { fcfa, kg, sig } from "../lib/format";
import { useApi } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { useRouter } from "../lib/router";
import type { Assumptions as AssumptionsData } from "../lib/types";

function show(value: unknown, lang: "fr" | "en"): string {
  if (typeof value === "number") return sig(value, lang);
  if (Array.isArray(value)) return value.map((v) => show(v, lang)).join(" – ");
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${k}: ${show(v, lang)}`)
      .join(", ");
  }
  return String(value);
}

/** Model, parameters, sources and known limits, readable by every role (FR-22). */
export function Assumptions() {
  const { t, td, lang } = useI18n();
  const { search } = useRouter();
  const productCode = search.get("product") || "tomato";
  const data = useApi<AssumptionsData>(`/assumptions?product=${encodeURIComponent(productCode)}`);
  if (data.error) {
    return (
      <div className="page">
        <ErrorState error={data.error} onRetry={data.reload} />
      </div>
    );
  }
  if (!data.data) {
    return (
      <div className="page">
        <Skeleton lines={6} />
      </div>
    );
  }
  const a = data.data;
  const source = (s: string) => td(`assumptions.source.${s}`, s);

  return (
    <div className="page page--reading">
      <h1>{t("assumptions.title")}</h1>
      <p className="lede">{t("assumptions.intro")}</p>
      <p className="tag">{t(`lot.product.${a.product}` as "lot.product.tomato")}</p>

      <section className="panel" aria-labelledby="model-title">
        <h2 id="model-title">{t("assumptions.model")}</h2>
        <p>{t("assumptions.modelText", { name: a.model.production, version: a.model.version })}</p>
        {a.model.fallback && <Notice tone="warn">{t("assumptions.fallbackNote")}</Notice>}
        {a.model.experimental && (
          <p className="muted">
            {t("assumptions.experimental", { name: a.model.experimental, verdict: a.model.verdict ?? "—" })}
          </p>
        )}
      </section>

      <section className="panel" aria-labelledby="limits-title">
        <h2 id="limits-title">{t("assumptions.limits")}</h2>
        <ul className="limits">
          {a.limits.map((code) => (
            <li key={code}>{td(`limit.${code}`, code)}</li>
          ))}
        </ul>
      </section>

      <section className="panel" aria-labelledby="params-title">
        <h2 id="params-title">{t("assumptions.params")}</h2>
        <div className="table-wrap">
          <table className="table table--params">
            <thead>
              <tr>
                <th scope="col">{t("assumptions.colName")}</th>
                <th scope="col">{t("assumptions.colValue")}</th>
                <th scope="col">{t("assumptions.colSource")}</th>
              </tr>
            </thead>
            <tbody>
              {a.parameters.map((p) => (
                <tr key={p.name}>
                  <th scope="row">
                    <span className="table__name">{p.description || p.name}</span>
                    {p.note && <span className="muted small table__note">{p.note}</span>}
                  </th>
                  <td className="num">
                    {show(p.value, lang)} {p.unit !== "-" ? p.unit : ""}
                  </td>
                  <td>
                    <span className={`tag tag--${p.source}`}>{source(p.source)}</span>
                    {p.reference && <span className="muted small table__note">{t("assumptions.reference")}{lang === "fr" ? " : " : ": "}{p.reference}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="eco-title">
        <h2 id="eco-title">{t("assumptions.economics")}</h2>
        <div className="table-wrap">
          <table className="table">
            <tbody>
              {a.economics.map((e) => (
                <tr key={e.name}>
                  <th scope="row">{td(`assume.${e.name}`, td(`eco.${e.name}`, e.name))}</th>
                  <td className="num">
                    {sig(e.value, lang)} {e.unit}
                  </td>
                  <td>
                    <span className={`tag tag--${e.source}`}>{source(e.source)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="markets-title">
        <h2 id="markets-title">{t("assumptions.markets")}</h2>
        <p className="muted small">{t("admin.markets")}</p>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t("form.destination")}</th>
                <th scope="col">{t("assumptions.price")}</th>
                <th scope="col">{t("assumptions.absorption")}</th>
              </tr>
            </thead>
            <tbody>
              {a.markets.map((m) => (
                <tr key={m.id}>
                  <th scope="row">
                    {m.name} <span className="muted">({m.city})</span>
                    {m.assumption_note && <span className="muted small table__note">{m.assumption_note}</span>}
                  </th>
                  <td className="num">{fcfa(m.ref_price_fcfa_kg, lang)}/kg</td>
                  <td className="num">{kg(m.absorption_kg_day, lang)}{lang === "fr" ? "/j" : "/day"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <p className="muted small">SHA-256 {a.product_file_sha256.slice(0, 12)}</p>
    </div>
  );
}
