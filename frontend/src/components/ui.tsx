// Shared, accessible building blocks: fields, notices, states and source badges.

import { useId, type ReactNode, type InputHTMLAttributes, type SelectHTMLAttributes } from "react";

import { ApiError, NETWORK_ERROR } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Link } from "../lib/router";

export function Field({
  label,
  hint,
  error,
  children,
  id,
  optional,
}: {
  label: string;
  hint?: ReactNode;
  error?: string;
  children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode;
  id?: string;
  optional?: boolean;
}) {
  const { t } = useI18n();
  const auto = useId();
  const fieldId = id ?? auto;
  const hintId = hint ? `${fieldId}-hint` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={`field${error ? " field--error" : ""}`}>
      <label htmlFor={fieldId}>
        {label}
        {optional && <span className="field__optional"> ({t("common.optional")})</span>}
      </label>
      {children({ id: fieldId, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint && (
        <p className="field__hint" id={hintId}>
          {hint}
        </p>
      )}
      {error && (
        <p className="field__error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="input" {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className="input" {...props} />;
}

export function Segmented<T extends string>({
  legend,
  name,
  value,
  options,
  onChange,
  help,
}: {
  legend: string;
  name: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  help?: string;
}) {
  return (
    <fieldset className="segmented">
      <legend>{legend}</legend>
      <div className="segmented__options">
        {options.map((option) => (
          <label key={option.value} className={`segmented__option${option.value === value ? " is-active" : ""}`}>
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={option.value === value}
              onChange={() => onChange(option.value)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
      {help && <p className="field__hint">{help}</p>}
    </fieldset>
  );
}

export function Notice({ tone = "info", children, title }: { tone?: "info" | "warn" | "error" | "ok"; children: ReactNode; title?: string }) {
  return (
    <div className={`notice notice--${tone}`} role={tone === "error" ? "alert" : "status"}>
      {title && <strong className="notice__title">{title}</strong>}
      <div>{children}</div>
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="loading__dot" aria-hidden="true" />
      {label}
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} style={{ width: `${90 - i * 15}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const { t } = useI18n();
  let message = error.message || t("common.error");
  if (error.code === NETWORK_ERROR) message = t("common.network");
  else if (error.status === 429) message = t("common.rateLimited", { s: error.retryAfter ?? 60 });
  else if (error.status === 404) message = t("common.notFound");
  else if (error.status >= 500) message = t("common.error");
  return (
    <Notice tone="error">
      <p>{message}</p>
      {error.requestId && <p className="muted small">{t("common.requestId", { id: error.requestId })}</p>}
      <div className="row-actions">
        {onRetry && (
          <button type="button" className="button button--quiet" onClick={onRetry}>
            {t("common.retry")}
          </button>
        )}
        {error.status === 404 && <Link to="/" className="button button--quiet">{t("common.backHome")}</Link>}
      </div>
    </Notice>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <svg viewBox="0 0 120 64" aria-hidden="true" className="empty__art">
        <rect x="8" y="24" width="104" height="30" rx="6" className="empty__crate" />
        <path d="M8 34h104M8 44h104" className="empty__slat" />
        <circle cx="38" cy="18" r="10" className="empty__fruit empty__fruit--a" />
        <circle cx="60" cy="16" r="10" className="empty__fruit empty__fruit--b" />
        <circle cx="82" cy="18" r="10" className="empty__fruit empty__fruit--c" />
      </svg>
      <h2>{title}</h2>
      {children}
      {action}
    </div>
  );
}

/** Where a value comes from (DAT-01): measured, automatic, user-entered or an assumption. */
export function SourceBadge({ source }: { source: string }) {
  const { t } = useI18n();
  const s = source.toLowerCase();
  let key: Parameters<typeof t>[0] = "source.assumption";
  let tone = "assumption";
  if (s === "manual" || s.startsWith("manual")) {
    key = "source.manual";
    tone = "manual";
  } else if (s === "open-meteo") {
    key = "source.open-meteo";
    tone = "auto";
  } else if (s === "user") {
    key = "source.user";
    tone = "manual";
  } else if (s.startsWith("organization")) {
    key = "source.organization";
    tone = "manual";
  } else if (s.startsWith("reference")) {
    key = "source.reference";
  } else if (s.startsWith("distances.csv")) {
    key = "source.table";
  } else if (s.startsWith("osrm")) {
    key = "source.osrm";
    tone = "auto";
  } else if (s.startsWith("default")) {
    key = "source.default";
  }
  return (
    <span className={`badge badge--${tone}`} title={source}>
      {t(key)}
    </span>
  );
}

export function Disclaimer() {
  const { t } = useI18n();
  return (
    <p className="disclaimer">
      {t("app.disclaimer")} <Link to="/assumptions">{t("app.disclaimerLink")}</Link>
    </p>
  );
}
