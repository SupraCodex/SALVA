# Runbook

## Run locally with Docker

```bash
cp .env.example .env          # set JWT_SECRET (python -c "import secrets; print(secrets.token_urlsafe(48))")
docker compose up --build     # PostgreSQL + API + interface on http://localhost:8000
```

At start-up the container applies migrations (`alembic upgrade head`) and loads the reference
locations and markets (`python -m app.seed --reference`). With `SEED_DEMO=true` it also creates
the demonstration workspace; the demo password comes from `DEMO_USER_PASSWORD`, or is generated
and printed once in the container log.

## Run locally without Docker

Requirements: Python 3.11+, Node 20+, PostgreSQL 16.

```bash
make install                  # Python packages (editable) and frontend dependencies
export DATABASE_URL=postgresql+psycopg://salva:salva@localhost:5432/salva
make demo                     # migrations + reference data + demo workspace
make run                      # builds the interface, serves everything on :8000
```

Without network access set `WEATHER_ENABLED=false`: the analysis then uses the default
temperature and labels it as an assumption.

## Configuration

All settings are environment variables (see `.env.example` and `backend/app/config.py`).
Production (`ENV=production`) refuses to start with the development JWT secret or a `*`
CORS origin, and marks the refresh cookie `Secure` (serve over HTTPS).

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection (SQLAlchemy URL, psycopg driver) |
| `JWT_SECRET` | Signing key of access tokens, at least 32 characters |
| `ALLOWED_ORIGINS` | Comma-separated origins allowed by CORS |
| `WEATHER_ENABLED` | Open-Meteo forecasts (no key) |
| `ROUTING_BASE_URL` | Optional OSRM-compatible service |
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` | Explanation provider: `template` (default), `gemini` or `openai` |

## Health and checks

- `GET /api/v1/health`: database status, explanation provider, weather flag, loss model.
- `./scripts/warmup.sh https://<host>` wakes a sleeping instance before a demo.
- API reference: `/api/docs` (OpenAPI at `/api/v1/openapi.json`).

## Updating the loss model

```bash
python -m ml.generate --seed 42
python -m ml.validate --dataset ml/artifacts/datasets/<id>
python -m ml.split    --dataset ml/artifacts/datasets/<id>
python -m ml.train    --split   ml/artifacts/splits/<dir>
python -m ml.evaluate --run ml/artifacts/runs/<v> --split ml/artifacts/splits/<dir>
python -m ml.package --run ml/artifacts/runs/<v> --report ml/reports/<v>
python -m ml.register --package ml/artifacts/models/<v> --report ml/reports/<v> [--promote]
```

`--promote` is refused unless the report's verdict is `LIGHTGBM GO`. Restart the application
after changing `ml/artifacts/active.json`.

## Tests

```bash
make test        # core, ml, backend (needs TEST_DATABASE_URL for PostgreSQL), frontend
make e2e         # browser scenarios against SALVA_URL (server running, reference data seeded)
```
