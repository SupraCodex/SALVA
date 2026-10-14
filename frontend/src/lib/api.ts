// Thin client for /api/v1. The access token lives in memory only; the refresh token is an
// HttpOnly cookie the browser sends to /api/v1/auth. A 401 triggers one silent refresh.

import type { TokenOut } from "./types";

export interface FieldError {
  field: string | null;
  code: string;
  message: string;
}

export class ApiError extends Error {
  status: number;
  code: string;
  errors: FieldError[];
  requestId: string | null;
  retryAfter: number | null;

  constructor(status: number, code: string, detail: string, errors: FieldError[] = [],
              requestId: string | null = null, retryAfter: number | null = null) {
    super(detail);
    this.status = status;
    this.code = code;
    this.errors = errors;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }

  /** Field-level messages keyed by field name (FR-02). */
  fieldMap(): Record<string, string> {
    const map: Record<string, string> = {};
    for (const e of this.errors) if (e.field && !map[e.field]) map[e.field] = e.message;
    return map;
  }
}

export const NETWORK_ERROR = "network-error";

let accessToken: string | null = null;
let refreshing: Promise<TokenOut | null> | null = null;
let onSessionChange: (session: TokenOut | null) => void = () => {};

export function setSessionListener(listener: (session: TokenOut | null) => void): void {
  onSessionChange = listener;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export async function parseError(response: Response): Promise<ApiError> {
  let body: { code?: string; detail?: string; errors?: FieldError[]; request_id?: string } = {};
  try {
    body = await response.json();
  } catch {
    body = {};
  }
  const retry = response.headers.get("Retry-After");
  return new ApiError(
    response.status,
    body.code ?? `http-${response.status}`,
    body.detail ?? response.statusText,
    Array.isArray(body.errors) ? body.errors : [],
    body.request_id ?? response.headers.get("X-Request-ID"),
    retry ? Number(retry) : null,
  );
}

async function rawFetch(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`/api/v1${path}`, { credentials: "same-origin", ...init });
  } catch {
    throw new ApiError(0, NETWORK_ERROR, "Network unavailable");
  }
}

export async function refreshSession(): Promise<TokenOut | null> {
  if (!refreshing) {
    refreshing = (async () => {
      const response = await rawFetch("/auth/refresh", {
        method: "POST",
        headers: { "X-Requested-With": "SALVA" },
      });
      if (!response.ok) {
        accessToken = null;
        onSessionChange(null);
        return null;
      }
      const session = (await response.json()) as TokenOut;
      accessToken = session.access_token;
      onSessionChange(session);
      return session;
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

export async function api<T>(path: string, options: { method?: string; body?: unknown; auth?: boolean } = {}): Promise<T> {
  const { method = "GET", body, auth = true } = options;
  const build = (): RequestInit => {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;
    if (path.startsWith("/auth/")) headers["X-Requested-With"] = "SALVA";
    return { method, headers, body: body === undefined ? undefined : JSON.stringify(body) };
  };
  let response = await rawFetch(path, build());
  if (response.status === 401 && auth && !path.startsWith("/auth/")) {
    const renewed = await refreshSession();
    if (renewed) response = await rawFetch(path, build());
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
