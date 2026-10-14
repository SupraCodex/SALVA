"""In-memory sliding-window rate limiter (SEC-05).

Single process by design for the MVP (no Redis, see design document §22); a multi-instance
deployment would need a shared store.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request

from app.errors import ApiError

_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def check(key: str, limit: int, window_s: int) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            retry = int(window_s - (now - q[0])) + 1
            raise ApiError(
                429,
                "rate-limited",
                "Too many requests, retry later.",
                headers={"Retry-After": str(retry), "RateLimit-Limit": str(limit)},
            )
        q.append(now)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def reset() -> None:
    with _lock:
        _hits.clear()


def count(key: str, window_s: int) -> int:
    """Number of events recorded for ``key`` within the window (no new event recorded)."""
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - window_s:
            q.popleft()
        return len(q)


def hit(key: str) -> None:
    with _lock:
        _hits[key].append(time.monotonic())


def clear(key: str) -> None:
    with _lock:
        _hits.pop(key, None)
