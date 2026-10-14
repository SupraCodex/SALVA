import { useState, type FormEvent } from "react";

import { Brand, LanguageSwitch } from "../components/Layout";
import { Disclaimer, Field, Input, Notice } from "../components/ui";
import { ApiError, NETWORK_ERROR } from "../lib/api";
import { useAuth } from "../lib/auth";
import { toApiError } from "../lib/hooks";
import { fieldErrors, useI18n } from "../lib/i18n";
import { Link, useRouter } from "../lib/router";

function useSubmit() {
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  };
  return { error, busy, run };
}

function AuthFrame({ title, intro, children }: { title: string; intro?: string; children: React.ReactNode }) {
  const { t } = useI18n();
  const steps = [
    { title: t("auth.step1Title"), text: t("auth.step1Text") },
    { title: t("auth.step2Title"), text: t("auth.step2Text") },
    { title: t("auth.step3Title"), text: t("auth.step3Text") },
  ];
  return (
    <div className="auth">
      <header className="auth__bar">
        <Brand tagline />
        <LanguageSwitch />
      </header>
      <div className="auth__body">
        <section className="auth__intro" aria-labelledby="auth-headline">
          <h1 id="auth-headline" className="auth__headline">{t("auth.headline")}</h1>
          <p className="auth__lead">{t("auth.pitch")}</p>
          <ol className="auth__steps">
            {steps.map((step, i) => (
              <li key={step.title}>
                <span className="auth__step-num" aria-hidden="true">{i + 1}</span>
                <span>
                  <strong>{step.title}</strong>
                  <span className="auth__step-text">{step.text}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>
        <section className="auth__panel" aria-labelledby="auth-title">
          <div className="auth__card">
            <h2 id="auth-title">{title}</h2>
            {intro && <p className="muted">{intro}</p>}
            {children}
          </div>
        </section>
      </div>
      <footer className="auth__foot">
        <Disclaimer />
      </footer>
    </div>
  );
}

function errorText(error: ApiError, t: ReturnType<typeof useI18n>["t"]): string {
  if (error.code === NETWORK_ERROR) return t("common.network");
  if (error.status === 429) return t("common.rateLimited", { s: error.retryAfter ?? 60 });
  return error.message;
}

export function LoginPage() {
  const { t } = useI18n();
  const { login } = useAuth();
  const { navigate, search } = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { error, busy, run } = useSubmit();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    run(async () => {
      await login(email, password);
      navigate(search.get("next") || "/", { replace: true });
    });
  };
  return (
    <AuthFrame title={t("auth.signInTitle")}>
      <form onSubmit={submit} noValidate className="stack">
        {error && <Notice tone="error">{errorText(error, t)}</Notice>}
        <Field label={t("auth.email")}>
          {(p) => <Input {...p} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <Field label={t("auth.password")}>
          {(p) => (
            <Input {...p} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          )}
        </Field>
        <button className="button button--primary" type="submit" disabled={busy}>
          {t("auth.signIn")}
        </button>
        <p className="muted">
          {t("auth.noAccount")} <Link to="/register">{t("auth.register")}</Link>
        </p>
      </form>
    </AuthFrame>
  );
}

export function RegisterPage() {
  const { t, td, lang } = useI18n();
  const { register } = useAuth();
  const { navigate } = useRouter();
  const [form, setForm] = useState({ email: "", password: "", organization: "" });
  const { error, busy, run } = useSubmit();
  const fields = error ? fieldErrors(error.errors, td) : {};
  const submit = (event: FormEvent) => {
    event.preventDefault();
    run(async () => {
      await register(form.email, form.password, form.organization, lang);
      navigate("/", { replace: true });
    });
  };
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [key]: e.target.value });
  return (
    <AuthFrame title={t("auth.registerTitle")} intro={t("auth.registerIntro")}>
      <form onSubmit={submit} noValidate className="stack">
        {error && !Object.keys(fields).length && <Notice tone="error">{errorText(error, t)}</Notice>}
        <Field label={t("auth.organization")} error={fields.organization_name}>
          {(p) => <Input {...p} required minLength={2} maxLength={120} value={form.organization} onChange={set("organization")} />}
        </Field>
        <Field label={t("auth.email")} error={fields.email}>
          {(p) => <Input {...p} type="email" autoComplete="email" required value={form.email} onChange={set("email")} />}
        </Field>
        <Field label={t("auth.password")} hint={t("auth.passwordHint")} error={fields.password}>
          {(p) => <Input {...p} type="password" autoComplete="new-password" required minLength={10} value={form.password} onChange={set("password")} />}
        </Field>
        <button className="button button--primary" type="submit" disabled={busy}>
          {t("auth.register")}
        </button>
        <p className="muted">
          {t("auth.haveAccount")} <Link to="/login">{t("auth.signIn")}</Link>
        </p>
      </form>
    </AuthFrame>
  );
}
