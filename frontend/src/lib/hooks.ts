import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "./api";

export interface Loadable<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
  setData: (value: T | null) => void;
}

/** GET a resource and keep it in state; `path === null` skips the request. */
export function useApi<T>(path: string | null): Loadable<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [tick, setTick] = useState(0);
  const current = useRef(0);

  useEffect(() => {
    if (path === null) {
      setLoading(false);
      return;
    }
    const id = ++current.current;
    setLoading(true);
    setError(null);
    api<T>(path)
      .then((value) => {
        if (id === current.current) setData(value);
      })
      .catch((err: unknown) => {
        if (id === current.current) setError(err instanceof ApiError ? err : new ApiError(0, "unknown", String(err)));
      })
      .finally(() => {
        if (id === current.current) setLoading(false);
      });
  }, [path, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload, setData };
}

export function toApiError(err: unknown): ApiError {
  return err instanceof ApiError ? err : new ApiError(0, "unknown", String(err));
}
