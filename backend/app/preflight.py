"""Start-up check run before migrations: readable messages instead of a silent restart loop.

    python -m app.preflight

Exits with status 1 and one explicit line per problem when the configuration cannot work
(missing secret, database URL left at its local default in production, database unreachable).
Secrets and passwords are never printed.
"""

from __future__ import annotations

import sys
import time

from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ATTEMPTS = 6
WAIT_S = 5


def _fail(lines: list[str]) -> int:
    for line in lines:
        print(f"PREFLIGHT ERROR: {line}", file=sys.stderr, flush=True)
    print(
        "PREFLIGHT: fix the environment variables of the service, then redeploy.", file=sys.stderr, flush=True
    )
    return 1


def main() -> int:
    try:
        from app.config import Settings

        settings = Settings()
    except ValidationError as exc:
        # Only the messages: the rejected values may be secrets.
        return _fail(
            [
                f"invalid configuration: {'.'.join(map(str, e['loc'])) or 'settings'}: {e['msg']}"
                for e in exc.errors()
            ]
        )

    url = make_url(settings.database_url)
    host = url.host or "?"
    problems = []
    if settings.env == "production" and host in {"localhost", "127.0.0.1"}:
        problems.append("DATABASE_URL is not set (it points to localhost); paste the Neon connection string")
    if problems:
        return _fail(problems)

    print(
        f"PREFLIGHT: env={settings.env} database_host={host} database={url.database} "
        f"weather={settings.weather_enabled} llm={settings.llm_provider}",
        flush=True,
    )
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 10}, pool_pre_ping=True)
    last_error = ""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"PREFLIGHT: database reachable (attempt {attempt})", flush=True)
            return 0
        except Exception as exc:  # noqa: BLE001 - every failure is reported the same way
            last_error = type(exc).__name__ + ": " + str(exc).splitlines()[0][:200]
            print(f"PREFLIGHT: database not reachable yet (attempt {attempt}/{ATTEMPTS})", flush=True)
            time.sleep(WAIT_S)
    return _fail([f"cannot connect to the database at {host}: {last_error}"])


if __name__ == "__main__":
    sys.exit(main())
