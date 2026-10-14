import { useState, type FormEvent } from "react";

import { ErrorState, Field, Input, Notice, Select, Skeleton } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, fcfa, kg } from "../lib/format";
import { toApiError, useApi } from "../lib/hooks";
import { fieldErrors, useI18n } from "../lib/i18n";
import type { Location, Market, StorageSite, UserRow } from "../lib/types";

type Mode = StorageSite["temp_mode"];
const MODES: Mode[] = ["ambient_shade", "ventilated", "cold_room"];

function useSubmit() {
  const { td } = useI18n();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<ApiError | null>(null);
  const run = async (fn: () => Promise<unknown>): Promise<boolean> => {
    setErrors({});
    setFailure(null);
    try {
      await fn();
      return true;
    } catch (err) {
      const e = toApiError(err);
      const mapped = fieldErrors(e.errors, td);
      if (Object.keys(mapped).length) setErrors(mapped);
      else setFailure(e);
      return false;
    }
  };
  return { errors, failure, run, setErrors };
}

function StorageSites() {
  const { t, lang } = useI18n();
  const sites = useApi<StorageSite[]>("/storage-sites");
  const locations = useApi<Location[]>("/locations");
  const { errors, failure, run, setErrors } = useSubmit();
  const [name, setName] = useState("");
  const [locationId, setLocationId] = useState("");
  const [capacity, setCapacity] = useState("");
  const [mode, setMode] = useState<Mode>("ventilated");
  const [cost, setCost] = useState("0");
  const [message, setMessage] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage(null);
    const local: Record<string, string> = {};
    if (name.trim().length < 2) local.name = t("common.required");
    if (!locationId) local.location_id = t("common.required");
    if (!(Number(capacity) > 0)) local.capacity_kg = t("err.greater_than", { limit: 0 });
    if (!(Number(cost) >= 0)) local.cost_fcfa_kg_day = t("err.greater_than_equal", { limit: 0 });
    if (Object.keys(local).length) {
      setErrors(local);
      return;
    }
    const ok = await run(() =>
      api<StorageSite>("/storage-sites", {
        method: "POST",
        body: {
          name: name.trim(),
          location_id: locationId,
          capacity_kg: Number(capacity),
          temp_mode: mode,
          cost_fcfa_kg_day: Number(cost),
        },
      }),
    );
    if (ok) {
      setName("");
      setCapacity("");
      setMessage(t("admin.siteAdded"));
      sites.reload();
    }
  };

  const toggle = async (site: StorageSite) => {
    const ok = await run(() =>
      api(`/storage-sites/${site.id}`, { method: "PATCH", body: { is_active: !site.is_active } }),
    );
    if (ok) sites.reload();
  };

  return (
    <section className="panel" aria-labelledby="sites-title">
      <h2 id="sites-title">{t("admin.sites")}</h2>
      <p className="muted">{t("admin.sitesIntro")}</p>
      {failure && <ErrorState error={failure} />}
      {sites.error && <ErrorState error={sites.error} onRetry={sites.reload} />}
      {!sites.data && !sites.error && <Skeleton lines={2} />}
      {sites.data && sites.data.length === 0 && <p>{t("admin.noSites")}</p>}
      {sites.data && sites.data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t("admin.siteName")}</th>
                <th scope="col">{t("admin.siteCapacity")}</th>
                <th scope="col">{t("admin.siteMode")}</th>
                <th scope="col">{t("admin.siteCost")}</th>
                <th scope="col">
                  <span className="sr-only">{t("admin.siteActive")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {sites.data.map((s) => (
                <tr key={s.id} className={s.is_active ? "" : "is-muted"}>
                  <th scope="row">
                    {s.name}
                    <span className="muted small table__note">{s.location_label}</span>
                  </th>
                  <td className="num">{kg(s.capacity_kg, lang)}</td>
                  <td>{t(`admin.mode.${s.temp_mode}`)}</td>
                  <td className="num">{fcfa(s.cost_fcfa_kg_day, lang)}</td>
                  <td>
                    <button type="button" className="link-button" onClick={() => toggle(s)}>
                      {s.is_active ? t("admin.siteDeactivate") : t("admin.siteActivate")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form className="admin-form" onSubmit={submit} noValidate>
        {message && <Notice tone="ok">{message}</Notice>}
        <div className="grid-3">
          <Field label={t("admin.siteName")} error={errors.name}>
            {(p) => <Input {...p} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label={t("admin.siteLocation")} error={errors.location_id}>
            {(p) => (
              <Select {...p} value={locationId} onChange={(e) => setLocationId(e.target.value)}>
                <option value="">{t("form.choose")}</option>
                {(locations.data ?? []).map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("admin.siteCapacity")} error={errors.capacity_kg}>
            {(p) => (
              <Input {...p} type="number" min={1} inputMode="decimal" value={capacity} onChange={(e) => setCapacity(e.target.value)} />
            )}
          </Field>
          <Field label={t("admin.siteMode")} error={errors.temp_mode}>
            {(p) => (
              <Select {...p} value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
                {MODES.map((m) => (
                  <option key={m} value={m}>
                    {t(`admin.mode.${m}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("admin.siteCost")} error={errors.cost_fcfa_kg_day}>
            {(p) => (
              <Input {...p} type="number" min={0} inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
            )}
          </Field>
        </div>
        <button type="submit" className="button button--primary">
          {t("admin.siteAdd")}
        </button>
      </form>
    </section>
  );
}

function MarketRow({ market, onSaved }: { market: Market; onSaved: (m: Market) => void }) {
  const { t, td, lang } = useI18n();
  const [price, setPrice] = useState(market.org_price_fcfa_kg?.toString() ?? "");
  const [absorption, setAbsorption] = useState(market.org_absorption_kg_day?.toString() ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const save = async (body: { price_fcfa_kg: number | null; absorption_kg_day: number | null }) => {
    setBusy(true);
    setErrors({});
    try {
      const updated = await api<Market>(`/markets/${market.id}`, { method: "PATCH", body });
      setPrice(updated.org_price_fcfa_kg?.toString() ?? "");
      setAbsorption(updated.org_absorption_kg_day?.toString() ?? "");
      onSaved(updated);
    } catch (err) {
      const e = toApiError(err);
      const mapped = fieldErrors(e.errors, td);
      setErrors(Object.keys(mapped).length ? mapped : { _: e.message });
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const local: Record<string, string> = {};
    if (price && !(Number(price) > 0)) local.price_fcfa_kg = t("err.greater_than", { limit: 0 });
    if (absorption && !(Number(absorption) >= 0)) local.absorption_kg_day = t("err.greater_than_equal", { limit: 0 });
    if (Object.keys(local).length) {
      setErrors(local);
      return;
    }
    save({ price_fcfa_kg: price ? Number(price) : null, absorption_kg_day: absorption ? Number(absorption) : null });
  };

  return (
    <li className="market-row">
      <form className="market-row__form" onSubmit={submit} noValidate>
        <div className="market-row__name">
          <strong>{market.name}</strong> <span className="muted">({market.city})</span>
          <span className="muted small">
            {t("admin.markets.reference")}
            {lang === "fr" ? " : " : ": "}
            {fcfa(market.ref_price_fcfa_kg, lang)}/kg, {kg(market.absorption_kg_day, lang)}
            {lang === "fr" ? "/jour" : "/day"}
          </span>
        </div>
        <Field label={t("admin.markets.price")} error={errors.price_fcfa_kg} optional>
          {(p) => (
            <Input {...p} type="number" min={1} inputMode="decimal" value={price}
              placeholder={String(market.ref_price_fcfa_kg)} onChange={(e) => setPrice(e.target.value)} />
          )}
        </Field>
        <Field label={t("admin.markets.absorption")} error={errors.absorption_kg_day} optional>
          {(p) => (
            <Input {...p} type="number" min={0} inputMode="decimal" value={absorption}
              placeholder={String(market.absorption_kg_day)} onChange={(e) => setAbsorption(e.target.value)} />
          )}
        </Field>
        <div className="row-actions">
          <button type="submit" className="button button--primary button--small" disabled={busy}>
            {t("admin.markets.save")}
          </button>
          {(market.org_price_fcfa_kg !== null || market.org_absorption_kg_day !== null) && (
            <button type="button" className="button button--quiet button--small" disabled={busy}
              onClick={() => save({ price_fcfa_kg: null, absorption_kg_day: null })}>
              {t("admin.markets.reset")}
            </button>
          )}
        </div>
        {errors._ && <p className="field__error">{errors._}</p>}
      </form>
    </li>
  );
}

function Markets() {
  const { t } = useI18n();
  const markets = useApi<Market[]>("/markets");
  const [message, setMessage] = useState<string | null>(null);
  const replace = (m: Market) => {
    markets.setData((markets.data ?? []).map((x) => (x.id === m.id ? m : x)));
    setMessage(t("admin.markets.saved"));
  };
  return (
    <section className="panel" aria-labelledby="markets-title">
      <h2 id="markets-title">{t("admin.markets.title")}</h2>
      <p className="muted">{t("admin.markets.intro")}</p>
      {message && <Notice tone="ok">{message}</Notice>}
      {markets.error && <ErrorState error={markets.error} onRetry={markets.reload} />}
      {!markets.data && !markets.error && <Skeleton lines={3} />}
      {markets.data && (
        <ul className="market-list">
          {markets.data.map((m) => (
            <MarketRow key={m.id} market={m} onSaved={replace} />
          ))}
        </ul>
      )}
    </section>
  );
}

function Users() {
  const { t, lang } = useI18n();
  const { user } = useAuth();
  const users = useApi<UserRow[]>("/admin/users");
  const { errors, failure, run, setErrors } = useSubmit();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRow["role"]>("operator");
  const [message, setMessage] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage(null);
    const local: Record<string, string> = {};
    if (!email.includes("@")) local.email = t("common.required");
    if (password.length < 10) local.password = t("auth.passwordHint");
    if (Object.keys(local).length) {
      setErrors(local);
      return;
    }
    const ok = await run(() =>
      api<UserRow>("/admin/users", { method: "POST", body: { email: email.trim(), password, role, locale: lang } }),
    );
    if (ok) {
      setEmail("");
      setPassword("");
      setMessage(t("admin.userAdded"));
      users.reload();
    }
  };

  const patch = async (row: UserRow, body: Partial<Pick<UserRow, "role" | "is_active">>) => {
    if (await run(() => api(`/admin/users/${row.id}`, { method: "PATCH", body }))) users.reload();
  };

  return (
    <section className="panel" aria-labelledby="users-title">
      <h2 id="users-title">{t("admin.users")}</h2>
      {failure && <ErrorState error={failure} />}
      {users.error && <ErrorState error={users.error} onRetry={users.reload} />}
      {!users.data && !users.error && <Skeleton lines={2} />}
      {users.data && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t("auth.email")}</th>
                <th scope="col">{t("admin.role")}</th>
                <th scope="col">
                  <span className="sr-only">{t("admin.userActive")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {users.data.map((u) => {
                const self = u.id === user?.id;
                return (
                  <tr key={u.id} className={u.is_active ? "" : "is-muted"}>
                    <th scope="row">
                      {u.email}
                      {self && <span className="muted"> ({t("admin.you")})</span>}
                      <span className="muted small table__note">
                        {u.is_active ? t("admin.userActive") : t("admin.userInactive")} — {dateTime(u.created_at, lang)}
                      </span>
                    </th>
                    <td>
                      {self ? (
                        t(`admin.role.${u.role}`)
                      ) : (
                        <Select
                          aria-label={`${t("admin.role")} ${u.email}`}
                          value={u.role}
                          onChange={(e) => patch(u, { role: e.target.value as UserRow["role"] })}
                        >
                          <option value="operator">{t("admin.role.operator")}</option>
                          <option value="admin">{t("admin.role.admin")}</option>
                        </Select>
                      )}
                    </td>
                    <td>
                      {!self && (
                        <button type="button" className="link-button" onClick={() => patch(u, { is_active: !u.is_active })}>
                          {u.is_active ? t("admin.deactivate") : t("admin.activate")}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <form className="admin-form" onSubmit={submit} noValidate>
        {message && <Notice tone="ok">{message}</Notice>}
        <div className="grid-3">
          <Field label={t("auth.email")} error={errors.email}>
            {(p) => <Input {...p} type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />}
          </Field>
          <Field label={t("admin.password")} hint={t("auth.passwordHint")} error={errors.password}>
            {(p) => (
              <Input {...p} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            )}
          </Field>
          <Field label={t("admin.role")} error={errors.role}>
            {(p) => (
              <Select {...p} value={role} onChange={(e) => setRole(e.target.value as UserRow["role"])}>
                <option value="operator">{t("admin.role.operator")}</option>
                <option value="admin">{t("admin.role.admin")}</option>
              </Select>
            )}
          </Field>
        </div>
        <button type="submit" className="button button--primary">
          {t("admin.userAdd")}
        </button>
      </form>
    </section>
  );
}

export function Admin() {
  const { t } = useI18n();
  const { user } = useAuth();
  if (user?.role !== "admin") {
    return (
      <div className="page">
        <Notice tone="warn">{t("admin.adminOnly")}</Notice>
      </div>
    );
  }
  return (
    <div className="page">
      <h1>{t("admin.title")}</h1>
      <StorageSites />
      <Markets />
      <Users />
    </div>
  );
}
