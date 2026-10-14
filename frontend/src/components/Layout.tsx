import { useState, type ReactNode } from "react";

import { useAuth } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import { Link, useRouter } from "../lib/router";
import type { Lang } from "../lib/types";
import { Disclaimer } from "./ui";

export function Brand({ tagline = false }: { tagline?: boolean }) {
  const { t } = useI18n();
  return (
    <Link to="/" className="brand" aria-label="SALVA">
      <svg viewBox="0 0 28 28" className="brand__mark" aria-hidden="true">
        <rect x="1" y="1" width="26" height="26" rx="6" className="brand__tile" />
        <rect x="6" y="12" width="16" height="4.5" rx="2.25" className="brand__band" />
        <rect x="12" y="9" width="2.2" height="10.5" rx="1.1" className="brand__tick" />
      </svg>
      <span className="brand__text">
        <span className="brand__name">SALVA</span>
        {tagline && <span className="brand__tagline">{t("app.tagline")}</span>}
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
  const signOut = async () => {
    await logout();
    navigate("/login", { replace: true });
  };
  return (
    <div className="shell">
      <a className="skip" href="#main">
        {t("app.skip")}
      </a>
      <header className="topbar">
        <div className="topbar__inner">
          <Brand />
          <nav id="main-nav" className={`nav${open ? " is-open" : ""}`} aria-label={t("nav.menu")}>
            <ul className="nav__list">
              {items.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className={`nav__link${item.active ? " is-active" : ""}`}
                    aria-current={item.active ? "page" : undefined}
                    onClick={() => setOpen(false)}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
            <div className="nav__account">
              <LanguageSwitch />
              {user && (
                <div className="account">
                  <span className="account__org">{user.organization_name}</span>
                  <span className="account__email">{user.email}</span>
                  <button type="button" className="link-button account__out" onClick={signOut}>
                    {t("nav.signOut")}
                  </button>
                </div>
              )}
            </div>
          </nav>
          <button
            type="button"
            className="topbar__menu"
            aria-expanded={open}
            aria-controls="main-nav"
            onClick={() => setOpen((v) => !v)}
          >
            <span className="topbar__menu-icon" aria-hidden="true" />
            {t("nav.menu")}
          </button>
        </div>
      </header>
      <main id="main" className="main" tabIndex={-1}>
        {children}
      </main>
      <footer className="footer">
        <Disclaimer />
      </footer>
    </div>
  );
}
