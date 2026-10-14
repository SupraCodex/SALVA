// Minimal history-API router: the app has a handful of routes, a dependency is not needed.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type AnchorHTMLAttributes, type ReactNode } from "react";

interface RouterState {
  path: string;
  search: URLSearchParams;
  navigate: (to: string, options?: { replace?: boolean }) => void;
}

const Context = createContext<RouterState | null>(null);

export function RouterProvider({ children }: { children: ReactNode }) {
  const [location, setLocation] = useState(() => ({ path: window.location.pathname, search: window.location.search }));
  useEffect(() => {
    const onPop = () => setLocation({ path: window.location.pathname, search: window.location.search });
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const navigate = useCallback((to: string, options: { replace?: boolean } = {}) => {
    if (options.replace) window.history.replaceState(null, "", to);
    else window.history.pushState(null, "", to);
    const url = new URL(to, window.location.origin);
    setLocation({ path: url.pathname, search: url.search });
    window.scrollTo(0, 0);
  }, []);
  const value = useMemo(
    () => ({ path: location.path, search: new URLSearchParams(location.search), navigate }),
    [location, navigate],
  );
  return (
    <Context.Provider value={value}>
      {children}
    </Context.Provider>
  );
}

export function useRouter(): RouterState {
  const ctx = useContext(Context);
  if (!ctx) throw new Error("useRouter outside RouterProvider");
  return ctx;
}

/** Match "/lots/:id/analysis" against a path; returns params or null. */
export function match(pattern: string, path: string): Record<string, string> | null {
  const p = pattern.split("/").filter(Boolean);
  const s = path.replace(/\/+$/, "").split("/").filter(Boolean);
  if (p.length !== s.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < p.length; i += 1) {
    if (p[i].startsWith(":")) params[p[i].slice(1)] = decodeURIComponent(s[i]);
    else if (p[i] !== s[i]) return null;
  }
  return params;
}

export function Link({ to, children, ...rest }: { to: string; children: ReactNode } & AnchorHTMLAttributes<HTMLAnchorElement>) {
  const { navigate } = useRouter();
  return (
    <a
      href={to}
      {...rest}
      onClick={(event) => {
        rest.onClick?.(event);
        if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
        event.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}
