import { useEffect } from "react";

import { Layout } from "./components/Layout";
import { EmptyState, Spinner } from "./components/ui";
import { useAuth } from "./lib/auth";
import { useI18n } from "./lib/i18n";
import { Link, match, useRouter } from "./lib/router";
import { Admin } from "./pages/Admin";
import { Assumptions } from "./pages/Assumptions";
import { LoginPage, RegisterPage } from "./pages/Auth";
import { Dashboard } from "./pages/Dashboard";
import { History } from "./pages/History";
import { LotHub, type Tab } from "./pages/LotHub";
import { NewLot } from "./pages/NewLot";

const TABS: Tab[] = ["analysis", "simulation", "recommendation", "history"];
const PUBLIC = ["/login", "/register"];

function Redirect({ to }: { to: string }) {
  const { navigate } = useRouter();
  useEffect(() => navigate(to, { replace: true }), [to, navigate]);
  return null;
}

function NotFound() {
  const { t } = useI18n();
  return (
    <div className="page">
      <EmptyState
        title={t("common.notFound")}
        action={
          <Link to="/" className="button button--primary">
            {t("common.backHome")}
          </Link>
        }
      />
    </div>
  );
}

function Screen({ path }: { path: string }) {
  if (path === "/" || path === "") return <Dashboard />;
  if (path === "/lots/new") return <NewLot />;
  if (path === "/history") return <History />;
  if (path === "/assumptions") return <Assumptions />;
  if (path === "/admin") return <Admin />;
  const bare = match("/lots/:id", path);
  if (bare) return <Redirect to={`/lots/${encodeURIComponent(bare.id)}/analysis`} />;
  const tabbed = match("/lots/:id/:tab", path);
  if (tabbed && (TABS as string[]).includes(tabbed.tab)) {
    return <LotHub key={tabbed.id} id={tabbed.id} tab={tabbed.tab as Tab} />;
  }
  return <NotFound />;
}

export function App() {
  const { t } = useI18n();
  const { user, ready } = useAuth();
  const { path, search } = useRouter();
  const clean = path.replace(/\/+$/, "") || "/";

  useEffect(() => {
    const titles: Record<string, string> = {
      "/": t("nav.dashboard"),
      "/lots/new": t("nav.newLot"),
      "/history": t("nav.history"),
      "/assumptions": t("nav.assumptions"),
      "/admin": t("nav.admin"),
      "/login": t("auth.signInTitle"),
      "/register": t("auth.registerTitle"),
    };
    document.title = titles[clean] ? `${titles[clean]} | SALVA` : "SALVA";
    // Move focus to the main region on navigation so screen readers announce the new page.
    document.getElementById("main")?.focus({ preventScroll: true });
  }, [clean, t]);

  if (!ready) {
    return (
      <div className="boot">
        <Spinner label={t("common.loading")} />
      </div>
    );
  }

  if (PUBLIC.includes(clean)) {
    if (user) return <Redirect to={search.get("next") || "/"} />;
    return clean === "/login" ? <LoginPage /> : <RegisterPage />;
  }
  if (!user) {
    const next = clean === "/" ? "" : `?next=${encodeURIComponent(clean + (search.toString() ? `?${search}` : ""))}`;
    return <Redirect to={`/login${next}`} />;
  }
  return (
    <Layout>
      <Screen path={clean} />
    </Layout>
  );
}
