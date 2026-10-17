import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { ErrorState, Field, Input, Notice, Segmented, Select, Skeleton, SourceBadge } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { addHours, fcfa, fromLocalInput, hours, num, toLocalInput } from "../lib/format";
import { toApiError, useApi } from "../lib/hooks";
import { fieldErrors, useI18n } from "../lib/i18n";
import { useRouter } from "../lib/router";
import { marketPrice } from "../lib/types";
import type { Enrichment, Location, Lot, Market, Maturity, Packaging, Product } from "../lib/types";

interface FormState {
  product_code: string;
  quantity_kg: string;
  harvested_at: string;
  maturity: Maturity;
  packaging: Packaging;
  origin_location_id: string;
  destination_market_id: string;
  eta_planned_at: string;
  delay_h: string;
  temp_override_c: string;
  price_override_fcfa_kg: string;
  notes: string;
}

const DRAFT_KEY = "salva.lotDraft";
const EMPTY: FormState = {
  product_code: "tomato",
  quantity_kg: "",
  harvested_at: "",
  maturity: "breaker",
  packaging: "crate",
  origin_location_id: "",
  destination_market_id: "",
  eta_planned_at: "",
  delay_h: "0",
  temp_override_c: "",
  price_override_fcfa_kg: "",
  notes: "",
};

function loadDraft(): FormState | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Partial<FormState>) } : null;
  } catch {
    return null;
  }
}

function saveDraft(state: FormState | null): void {
  try {
    if (state) localStorage.setItem(DRAFT_KEY, JSON.stringify(state));
    else localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* storage unavailable: the form still works */
  }
}

/** The design document's demonstration lot (§47), with dates relative to now. */
function exampleLot(locations: Location[], markets: Market[]): FormState {
  const now = new Date();
  const harvest = new Date(now.getTime() - 50 * 3_600_000);
  harvest.setMinutes(0, 0, 0);
  const eta = new Date(now.getTime() + 6 * 3_600_000);
  eta.setMinutes(0, 0, 0);
  return {
    ...EMPTY,
    quantity_kg: "500",
    harvested_at: toLocalInput(harvest),
    origin_location_id: locations.find((l) => l.code === "L01")?.id ?? locations[0]?.id ?? "",
    destination_market_id: markets.find((m) => m.code === "M01")?.id ?? markets[0]?.id ?? "",
    eta_planned_at: toLocalInput(eta),
    delay_h: "12",
  };
}

export function NewLot() {
  const { t, td, lang } = useI18n();
  const { navigate, search } = useRouter();
  const locations = useApi<Location[]>("/locations");
  const markets = useApi<Market[]>("/markets");
  const products = useApi<Product[]>("/products");
  const [form, setForm] = useState<FormState>(() => loadDraft() ?? EMPTY);
  const [restored] = useState(() => loadDraft() !== null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [enrichment, setEnrichment] = useState<Enrichment | null>(null);
  const [checking, setChecking] = useState(false);
  const etaTouched = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);

  const origins = useMemo(() => (locations.data ?? []).filter((l) => l.kind !== "market"), [locations.data]);
  const market = markets.data?.find((m) => m.id === form.destination_market_id);

  useEffect(() => {
    if (search.get("example") === "1" && locations.data && markets.data) {
      setForm(exampleLot(locations.data, markets.data));
      etaTouched.current = true;
    }
    // Only when the reference data arrives or the example is requested.
  }, [locations.data, markets.data]);

  useEffect(() => saveDraft(form), [form]);

  // Automatic enrichment preview: weather, route duration and reference price (FR-03).
  useEffect(() => {
    const harvested = fromLocalInput(form.harvested_at);
    if (!form.origin_location_id || !form.destination_market_id || !harvested) {
      setEnrichment(null);
      return;
    }
    let cancelled = false;
    setChecking(true);
    const handle = window.setTimeout(() => {
      api<Enrichment>("/lots/enrichment-preview", {
        method: "POST",
        body: {
          origin_location_id: form.origin_location_id,
          destination_market_id: form.destination_market_id,
          harvested_at: harvested,
          eta_current_at: fromLocalInput(form.eta_planned_at) ?? undefined,
        },
      })
        .then((value) => {
          if (cancelled) return;
          setEnrichment(value);
          if (!etaTouched.current && !form.eta_planned_at && value.suggested_eta_at) {
            setForm((f) => ({ ...f, eta_planned_at: toLocalInput(value.suggested_eta_at as string) }));
          }
        })
        .catch(() => !cancelled && setEnrichment(null))
        .finally(() => !cancelled && setChecking(false));
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [form.origin_location_id, form.destination_market_id, form.harvested_at, form.eta_planned_at]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => {
      const { [key]: _removed, ...rest } = e;
      return rest;
    });
  };

  const validate = (): Record<string, string> => {
    const out: Record<string, string> = {};
    const required = t("common.required");
    const quantity = Number(form.quantity_kg);
    if (!form.quantity_kg) out.quantity_kg = required;
    else if (!(quantity > 0)) out.quantity_kg = t("err.greater_than", { limit: 0 });
    else if (quantity > 100_000) out.quantity_kg = t("err.less_than_equal", { limit: 100000 });
    const harvested = fromLocalInput(form.harvested_at);
    if (!harvested) out.harvested_at = required;
    else if (new Date(harvested).getTime() > Date.now() + 3_600_000) out.harvested_at = t("err.future_date");
    if (!form.origin_location_id) out.origin_location_id = required;
    if (!form.destination_market_id) out.destination_market_id = required;
    const eta = fromLocalInput(form.eta_planned_at);
    if (!eta) out.eta_planned_at = required;
    else if (harvested && eta <= harvested) out.eta_planned_at = t("err.eta_order");
    const delay = Number(form.delay_h || 0);
    if (!(delay >= 0) || delay > 240) out.delay_h = t("err.greater_than_equal", { limit: 0 });
    if (form.temp_override_c && !(Number(form.temp_override_c) >= 0 && Number(form.temp_override_c) <= 50))
      out.temp_override_c = t("err.less_than_equal", { limit: 50 });
    if (form.price_override_fcfa_kg && !(Number(form.price_override_fcfa_kg) > 0))
      out.price_override_fcfa_kg = t("err.greater_than", { limit: 0 });
    return out;
  };

  const focusFirstError = (keys: string[]) => {
    window.setTimeout(() => {
      const first = keys.map((k) => formRef.current?.querySelector<HTMLElement>(`[name="${k}"]`)).find(Boolean);
      first?.focus();
    }, 0);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitError(null);
    const local = validate();
    if (Object.keys(local).length) {
      if (local.temp_override_c || local.price_override_fcfa_kg) setAdvanced(true);
      setErrors(local);
      focusFirstError(Object.keys(local));
      return;
    }
    const eta = fromLocalInput(form.eta_planned_at) as string;
    const body = {
      product_code: form.product_code,
      quantity_kg: Number(form.quantity_kg),
      harvested_at: fromLocalInput(form.harvested_at),
      maturity: form.maturity,
      packaging: form.packaging,
      origin_location_id: form.origin_location_id,
      destination_market_id: form.destination_market_id,
      eta_planned_at: eta,
      eta_current_at: addHours(eta, Number(form.delay_h || 0)),
      temp_override_c: form.temp_override_c ? Number(form.temp_override_c) : null,
      price_override_fcfa_kg: form.price_override_fcfa_kg ? Number(form.price_override_fcfa_kg) : null,
      notes: form.notes.trim() || null,
    };
    setBusy(true);
    try {
      const lot = await api<Lot>("/lots", { method: "POST", body });
      saveDraft(null);
      try {
        await api(`/lots/${lot.id}/analyses`, { method: "POST", body: {} });
      } catch {
        /* the lot exists; the analysis page offers to run it again */
      }
      navigate(`/lots/${lot.id}/analysis`);
    } catch (err) {
      const apiError = toApiError(err);
      const mapped = fieldErrors(apiError.errors, td);
      if (mapped._ && !mapped.eta_planned_at) mapped.eta_planned_at = mapped._;
      if (mapped.eta_current_at) mapped.delay_h = mapped.eta_current_at;
      delete mapped._;
      if (Object.keys(mapped).length) {
        setErrors(mapped);
        focusFirstError(Object.keys(mapped));
      } else setSubmitError(apiError);
    } finally {
      setBusy(false);
    }
  };

  if (locations.error || markets.error || products.error) {
    return (
      <div className="page">
        <ErrorState
          error={(locations.error ?? markets.error ?? products.error) as ApiError}
          onRetry={() => { locations.reload(); markets.reload(); products.reload(); }}
        />
      </div>
    );
  }
  if (!locations.data || !markets.data || !products.data) {
    return (
      <div className="page">
        <section className="panel panel--loading" aria-busy="true" aria-live="polite">
          <h1>{t("form.title")}</h1>
          <p className="muted">{t("form.loading")}</p>
          <Skeleton lines={6} />
        </section>
      </div>
    );
  }

  const suggestedEta =
    enrichment?.suggested_eta_at && form.harvested_at ? toLocalInput(enrichment.suggested_eta_at) : null;

  return (
    <div className="page page--narrow">
      <div className="page__head">
        <h1>{t("form.title")}</h1>
        <button
          type="button"
          className="button button--quiet"
          onClick={() => {
            setForm(exampleLot(locations.data as Location[], markets.data as Market[]));
            etaTouched.current = true;
            setErrors({});
          }}
        >
          {t("form.prefill")}
        </button>
      </div>
      <p className="lead">{t("form.intro")}</p>
      {restored && <p className="muted small">{t("form.draftRestored")}</p>}
      <form ref={formRef} className="lot-form" onSubmit={submit} noValidate>
        {Object.keys(errors).length > 0 && <Notice tone="error">{t("form.errorSummary")}</Notice>}
        {submitError && <ErrorState error={submitError} />}
        <div className="grid-2">
          <Field label={t("form.product")}>
            {(p) => (
              <Select {...p} name="product_code" value={form.product_code} onChange={(e) => set("product_code", e.target.value)}>
                {products.data.map((product) => (
                  <option key={product.code} value={product.code}>
                    {lang === "fr" ? product.label_fr : product.label_en}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("form.quantity")} error={errors.quantity_kg}>
            {(p) => (
              <Input {...p} name="quantity_kg" type="number" inputMode="decimal" min={1} max={100000} step="any" required
                value={form.quantity_kg} onChange={(e) => set("quantity_kg", e.target.value)} />
            )}
          </Field>
        </div>
        <Field label={t("form.harvested")} error={errors.harvested_at}>
          {(p) => (
            <Input {...p} name="harvested_at" type="datetime-local" required value={form.harvested_at}
              onChange={(e) => set("harvested_at", e.target.value)} />
          )}
        </Field>
        <Segmented
          legend={t("form.maturity")}
          name="maturity"
          value={form.maturity}
          onChange={(v) => set("maturity", v)}
          help={t("form.maturityHelp")}
          options={(["green", "breaker", "ripe"] as Maturity[]).map((m) => ({ value: m, label: t(`lot.maturity.${m}`) }))}
        />
        <Segmented
          legend={t("form.packaging")}
          name="packaging"
          value={form.packaging}
          onChange={(v) => set("packaging", v)}
          options={(["crate", "carton", "sack"] as Packaging[]).map((m) => ({ value: m, label: t(`lot.packaging.${m}`) }))}
        />
        <div className="grid-2">
          <Field label={t("form.origin")} error={errors.origin_location_id}>
            {(p) => (
              <Select {...p} name="origin_location_id" required value={form.origin_location_id}
                onChange={(e) => set("origin_location_id", e.target.value)}>
                <option value="">{t("form.choose")}</option>
                {origins.map((l) => (
                  <option key={l.id} value={l.id}>{l.label}</option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("form.destination")} error={errors.destination_market_id}>
            {(p) => (
              <Select {...p} name="destination_market_id" required value={form.destination_market_id}
                onChange={(e) => set("destination_market_id", e.target.value)}>
                <option value="">{t("form.choose")}</option>
                {(markets.data ?? []).map((m) => (
                  <option key={m.id} value={m.id}>{m.name} ({m.city})</option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        <div className="grid-2">
          <Field
            label={t("form.eta")}
            error={errors.eta_planned_at}
            hint={
              enrichment && enrichment.route_hours.value !== null ? (
                <>
                  {t("form.etaSuggested", { h: hours(enrichment.route_hours.value, lang) })}{" "}
                  <SourceBadge source={enrichment.route_hours.source} />{" "}
                  {suggestedEta && suggestedEta !== form.eta_planned_at && (
                    <button type="button" className="link-button" onClick={() => { etaTouched.current = true; set("eta_planned_at", suggestedEta); }}>
                      {t("form.useSuggested")}
                    </button>
                  )}
                </>
              ) : undefined
            }
          >
            {(p) => (
              <Input {...p} name="eta_planned_at" type="datetime-local" required value={form.eta_planned_at}
                onChange={(e) => { etaTouched.current = true; set("eta_planned_at", e.target.value); }} />
            )}
          </Field>
          <Field label={t("form.delay")} error={errors.delay_h}>
            {(p) => (
              <Input {...p} name="delay_h" type="number" inputMode="decimal" min={0} max={240} step="0.5"
                value={form.delay_h} onChange={(e) => set("delay_h", e.target.value)} />
            )}
          </Field>
        </div>

        <section className="enrich" aria-live="polite">
          <h2 className="enrich__title">{t("form.dataCheck")}</h2>
          {checking && <p className="muted small">{t("form.checking")}</p>}
          {!checking && enrichment && (
            enrichment.temperature_available ? (
              <p>
                {t("form.weatherOk", { t: `${num(enrichment.temperature.value, lang)} °C` })}{" "}
                <SourceBadge source={enrichment.temperature.source} />
              </p>
            ) : (
              <Notice tone="warn">
                {t("form.weatherDown", { t: `${num(enrichment.temperature.value, lang)} °C` })}{" "}
                <button type="button" className="link-button" onClick={() => setAdvanced(true)}>
                  {t("form.temp")}
                </button>
              </Notice>
            )
          )}
          {!checking && !enrichment && <p className="muted small">{t("form.enrichPending")}</p>}
        </section>

        <details className="advanced" open={advanced} onToggle={(e) => setAdvanced((e.target as HTMLDetailsElement).open)}>
          <summary>{t("form.advanced")}</summary>
          <div className="grid-2">
            <Field label={t("form.temp")} hint={t("form.tempHelp")} error={errors.temp_override_c} optional>
              {(p) => (
                <Input {...p} name="temp_override_c" type="number" inputMode="decimal" min={0} max={50} step="0.1"
                  value={form.temp_override_c} onChange={(e) => set("temp_override_c", e.target.value)} />
              )}
            </Field>
            <Field
              label={t("form.price")}
              hint={t("form.priceHelp", { price: market ? `${fcfa(marketPrice(market), lang)}/kg` : "–" })}
              error={errors.price_override_fcfa_kg}
              optional
            >
              {(p) => (
                <Input {...p} name="price_override_fcfa_kg" type="number" inputMode="decimal" min={1} step="1"
                  value={form.price_override_fcfa_kg} onChange={(e) => set("price_override_fcfa_kg", e.target.value)} />
              )}
            </Field>
          </div>
          <Field label={t("form.notes")} hint={t("form.notesHelp")} error={errors.notes} optional>
            {(p) => (
              <textarea {...p} name="notes" className="input" rows={2} maxLength={500} value={form.notes}
                onChange={(e) => set("notes", e.target.value)} />
            )}
          </Field>
        </details>

        <div className="form-actions">
          <button type="submit" className="button button--primary button--wide" disabled={busy}>
            {busy ? t("form.submitting") : t("form.submit")}
          </button>
        </div>
      </form>
    </div>
  );
}
