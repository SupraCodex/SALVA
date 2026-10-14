import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, refreshSession, setAccessToken, setSessionListener } from "./api";
import type { Lang, Me, TokenOut } from "./types";

interface AuthState {
  user: Me | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<Me>;
  register: (email: string, password: string, organization: string, locale: Lang) => Promise<Me>;
  logout: () => Promise<void>;
  updateLocale: (locale: Lang) => Promise<void>;
}

const Context = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setSessionListener((session) => setUser(session ? session.user : null));
    // A page reload keeps the session through the HttpOnly refresh cookie.
    refreshSession().finally(() => setReady(true));
  }, []);

  const accept = useCallback((session: TokenOut) => {
    setAccessToken(session.access_token);
    setUser(session.user);
    return session.user;
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      ready,
      login: async (email, password) =>
        accept(await api<TokenOut>("/auth/login", { method: "POST", body: { email, password }, auth: false })),
      register: async (email, password, organization, locale) =>
        accept(
          await api<TokenOut>("/auth/register", {
            method: "POST",
            body: { email, password, organization_name: organization, locale },
            auth: false,
          }),
        ),
      logout: async () => {
        try {
          await api<void>("/auth/logout", { method: "POST", auth: false });
        } finally {
          setAccessToken(null);
          setUser(null);
        }
      },
      updateLocale: async (locale) => {
        if (!user) return;
        setUser(await api<Me>("/me", { method: "PATCH", body: { locale } }));
      },
    }),
    [user, ready, accept],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Context);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
