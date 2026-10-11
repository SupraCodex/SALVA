"""In-memory sliding-window limiter (single process; no Redis for the MVP)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request

from app.config import get_settings
from app.errors import ApiError

_hits: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def check(key: str, limit: int, window_s: int = 60) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            retry = int(window_s - (now - q[0])) + 1
            raise ApiError(429, "rate-limited", "Too many requests, retry later.",
                           headers={"Retry-After": str(retry)})
        q.append(now)


def limit_by_ip(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    check(f"{request.url.path}:{ip}", get_settings().rate_limit_per_min)


def reset() -> None:
    with _lock:
        _hits.clear()
