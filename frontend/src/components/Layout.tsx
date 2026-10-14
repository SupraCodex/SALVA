import { useState, type ReactNode } from "react";

import { useAuth } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import { Link, useRouter } from "../lib/router";
import type { Lang } from "../lib/types";
import { Disclaimer } from "./ui";

export function Brand() {
  const { t } = useI18n();
  return (
    <Link to="/" className="brand" aria-label="SALVA">
      <svg viewBox="0 0 32 32" className="brand__mark" aria-hidden="true">
        <rect width="32" height="32" rx="7" />
        <rect x="6" y="14" width="20" height="5" rx="2.5" className="brand__band" />
        <rect x="13" y="11" width="2.4" height="11" rx="1.2" className="brand__tick" />
      </svg>
      <span className="brand__text">
        <span className="brand__name">SALVA</span>
        <span className="brand__tagline">{t("app.tagline")}</span>
      </span>
    </Link>
  );
}

export function LanguageSwitch() {
  const { lang, setLang, t } = useI18n();
  const { user, updateLocale } = useAuth();
  const choose = (next: Lang) => {
    setLang(next);
    if (user && user.locale !== next) updateLocale(next).catch(() => undefined);
  };
  return (
    <div className="lang" role="group" aria-label={t("nav.language")}>
      {(["fr", "en"] as Lang[]).map((code) => (
        <button
          key={code}
          type="button"
          className={`lang__option${lang === code ? " is-active" : ""}`}
          aria-pressed={lang === code}
          onClick={() => choose(code)}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const { user, logout } = useAuth();
  const { path, navigate } = useRouter();
  const [open, setOpen] = useState(false);
  const items = [
    { to: "/", label: t("nav.dashboard"), active: path === "/" || (path.startsWith("/lots/") && path !== "/lots/new") },
    { to: "/lots/new", label: t("nav.newLot"), active: path === "/lots/new" },
    { to: "/history", label: t("nav.history"), active: path === "/history" },
    { to: "/assumptions", label: t("nav.assumptions"), active: path === "/assumptions" },
    ...(user?.role === "admin" ? [{ to: "/admin", label: t("nav.admin"), active: path === "/admin" }] : []),
  ];
  return (
    <div className="shell">
      <a className="skip" href="#main">
        {t("app.skip")}
      </a>
      <header className="topbar">
        <Brand />
        <button
          type="button"
          className="topbar__menu button button--quiet"
          aria-expanded={open}
          aria-controls="main-nav"
          onClick={() => setOpen((v) => !v)}
        >
          {t("nav.menu")}
        </button>
      </header>
      <nav id="main-nav" className={`sidebar${open ? " is-open" : ""}`} aria-label={t("nav.menu")}>
        <ul className="sidebar__list">
          {items.map((item) => (
            <li key={item.to}>
              <Link
                to={item.to}
                className={`sidebar__link${item.active ? " is-active" : ""}`}
                aria-current={item.active ? "page" : undefined}
                onClick={() => setOpen(false)}
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
        <div className="sidebar__foot">
          <LanguageSwitch />
          {user && (
            <div className="sidebar__user">
              <span className="sidebar__org">{user.organization_name}</span>
              <span className="muted small">{user.email}</span>
              <button
                type="button"
                className="button button--quiet button--small"
                onClick={async () => {
                  await logout();
                  navigate("/login", { replace: true });
                }}
              >
                {t("nav.signOut")}
              </button>
            </div>
          )}
        </div>
      </nav>
      <main id="main" className="main" tabIndex={-1}>
        {children}
        <footer className="footer">
          <Disclaimer />
        </footer>
      </main>
    </div>
  );
}
