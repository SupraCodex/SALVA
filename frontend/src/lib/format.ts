// Locale-aware formatting. Times are shown in the user's time zone, with the zone named.

import type { Lang } from "./types";

const locales: Record<Lang, string> = { fr: "fr-FR", en: "en-GB" };

export function fcfa(value: number | null | undefined, lang: Lang): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  return `${new Intl.NumberFormat(locales[lang], { maximumFractionDigits: 0 }).format(Math.round(value))}\u00a0FCFA`;
}

export function kg(value: number | null | undefined, lang: Lang): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  return `${new Intl.NumberFormat(locales[lang], { maximumFractionDigits: 0 }).format(Math.round(value))}\u00a0kg`;
}

export function pct(fraction: number | null | undefined, lang: Lang): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return "–";
  return new Intl.NumberFormat(locales[lang], { style: "percent", maximumFractionDigits: 0 }).format(fraction);
}

export function num(value: number | null | undefined, lang: Lang, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  return new Intl.NumberFormat(locales[lang], { maximumFractionDigits: digits }).format(value);
}

/** Model parameters span several orders of magnitude: keep three significant digits. */
export function sig(value: number, lang: Lang): string {
  if (value !== 0 && Math.abs(value) < 1) {
    return new Intl.NumberFormat(locales[lang], { maximumSignificantDigits: 3 }).format(value);
  }
  return num(value, lang, 2);
}

export function hours(value: number | null | undefined, lang: Lang): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  return `${num(value, lang, value < 10 ? 1 : 0)}\u00a0h`;
}

export function dateTime(iso: string | null | undefined, lang: Lang): string {
  if (!iso) return "–";
  return new Intl.DateTimeFormat(locales[lang], {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(iso));
}

/** Value for <input type="datetime-local"> in the browser's time zone. */
export function toLocalInput(iso: string | Date): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Convert a datetime-local value (browser time zone) to an ISO UTC string, or null. */
export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function addHours(iso: string, h: number): string {
  return new Date(new Date(iso).getTime() + h * 3_600_000).toISOString();
}
