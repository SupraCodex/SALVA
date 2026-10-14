import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { en, fr, type MessageKey } from "./messages";
import type { Lang } from "./types";

const DICTS: Record<Lang, Record<MessageKey, string>> = { fr, en };
const STORAGE_KEY = "salva.lang";

export function translate(lang: Lang, key: MessageKey, vars: Record<string, string | number> = {}): string {
  const template = DICTS[lang][key] ?? fr[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name: string) => (name in vars ? String(vars[name]) : `{${name}}`));
}

/** Translate a dynamic key (e.g. "reason." + code); unknown codes fall back to the code itself. */
export function translateDynamic(lang: Lang, key: string, fallback?: string): string {
  return key in DICTS[lang] ? DICTS[lang][key as MessageKey] : (fallback ?? key);
}

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "fr" || saved === "en") return saved;
  } catch {
    /* storage unavailable */
  }
  return navigator.language?.toLowerCase().startsWith("en") ? "en" : "fr";
}

interface I18n {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
  td: (key: string, fallback?: string) => string;
}

const Context = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable */
    }
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  const value = useMemo<I18n>(
    () => ({
      lang,
      setLang,
      t: (key, vars) => translate(lang, key, vars),
      td: (key, fallback) => translateDynamic(lang, key, fallback),
    }),
    [lang, setLang],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Context);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}

const LIMIT = /(?:than|equal to)\s+(-?[\d.]+)/i;

/** Field errors of a problem+json response, translated when the error code is known (FR-02). */
export function fieldErrors(
  errors: { field: string | null; code: string; message: string }[],
  td: (key: string, fallback?: string) => string,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const e of errors) {
    const field = e.field ?? "_";
    if (out[field]) continue;
    const limit = LIMIT.exec(e.message)?.[1] ?? "";
    let code = e.code;
    if (code === "value_error" && /after harvested_at/.test(e.message)) code = "eta_order";
    const text = td(`err.${code}`, e.message);
    out[field] = text.replace("{limit}", limit);
  }
  return out;
}
