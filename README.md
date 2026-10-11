# SALVA — Backend API

REST API and PostgreSQL database of **SALVA** (*Spoilage-Aware Logistics & Value Allocation*), a decision-support
tool for perishable produce: given a lot (product, quantity, harvest time, maturity, packaging, route, ETA), it
estimates the risk of value loss and compares decisions — continue, store, reroute, sell locally or split the lot.

Built with FastAPI, Pydantic v2, SQLAlchemy 2, Alembic and PostgreSQL 16.

> Every figure returned is a **model estimate, not validated in the field**
> (`disclaimer_code: MODEL_ESTIMATE_NOT_FIELD_VALIDATED`).

## Run

### With Docker (API + PostgreSQL)
```bash
cd backend
docker compose up --build
```
API on http://localhost:8000 — interactive docs on http://localhost:8000/docs.
The container creates or upgrades the database schema (`alembic upgrade head`) before starting.

### Without Docker
Requires Python 3.11+ and PostgreSQL 16 with a `salva` database.
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
alembic upgrade head                                    # creates the tables
uvicorn app.main:app --reload
```

## Configuration
Read from environment variables or a `backend/.env` file (never commit it).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://salva:salva@localhost:5432/salva` | PostgreSQL connection |
| `ALLOWED_ORIGINS` | `["http://localhost:3000"]` | CORS origins (front-end) |
| `REFERENCE_DIR` | `../data/reference` | Folder with `distances.csv` (and `products.yaml` for the engine) |
| `WEATHER_ENABLED` | `true` | Use Open-Meteo for temperature; otherwise manual value or labelled default |
| `AUTH_ENABLED` | `false` | `false`: every request uses the `demo` organization. `true`: JWT required |
| `JWT_SECRET` | dev value | **Must be changed in production** |
| `SEED` | `42` | Fixed random seed: same inputs, same results |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Database, engine/model version, explanation layer, auth mode |
| GET | `/api/v1/reference` | Products, locations, markets, the organization's storage sites |
| POST | `/api/v1/storage-sites` | Add a storage site (admin) |
| POST | `/api/v1/lots` | Create a lot |
| GET | `/api/v1/lots` | List lots (`limit`, `offset`, `status`), newest first |
| GET | `/api/v1/lots/{id}` | Read a lot with its latest analysis |
| PATCH | `/api/v1/lots/{id}` | Update ETA, temperature, price or notes |
| POST | `/api/v1/lots/{id}/analyze` | Risk + simulation + allocation + recommendation in one call, stored |
| GET | `/api/v1/analyses/{id}` | Read a stored analysis |
| POST | `/api/v1/analyses/{id}/explanation` | Plain-language explanation, `{"lang": "fr" \| "en"}` |
| POST / GET | `/api/v1/lots/{id}/outcomes` | Record the decision taken and the real result |
| POST | `/api/v1/auth/register` · `/login` · `/logout` | Authentication (only when `AUTH_ENABLED=true`) |
| GET | `/api/v1/auth/me` | Current user |

`POST /analyze` accepts an optional body: `now` (replay an analysis at a past time), `n_draws`, `seed`,
`risk_profile` (`prudent` \| `balanced` \| `ambitious`), `absorb_override` (`{market_id: kg_per_day}`).

**Example**
```bash
curl -s -X POST localhost:8000/api/v1/lots -H 'Content-Type: application/json' -d '{
  "product": "tomato", "kg": 500, "harvested_at": "2026-10-09T06:00:00Z",
  "maturity": "breaker", "packaging": "crate", "origin_id": 4, "destination_id": 1,
  "eta_planned": "2026-10-11T12:00:00Z", "eta_current": "2026-10-12T00:00:00Z"}'
curl -s -X POST localhost:8000/api/v1/lots/1/analyze
```

**Errors** use `application/problem+json` (RFC 7807) with a `request_id`. Unknown fields are refused (422).
A resource that belongs to another organization answers 404, never 403.

## Project structure
```
backend/
├── app/
│   ├── main.py            FastAPI app, CORS, request id, logging, routers
│   ├── config.py          typed settings from environment / .env
│   ├── deps.py            current caller (demo organization or JWT user)
│   ├── errors.py          problem+json errors
│   ├── security.py        Argon2id password hashing, JWT
│   ├── rate_limit.py      in-memory rate limiter
│   ├── api/v1/            HTTP routes only, no business logic
│   ├── schemas/           Pydantic request / response contracts
│   ├── db/                SQLAlchemy session and models
│   ├── repositories/      SQL queries, always filtered by organization
│   ├── services/          use cases: lots, enrichment, options, analysis, explanation, outcomes, auth
│   └── integrations/      Open-Meteo client, road distances table
├── migrations/            Alembic schema migrations
├── Dockerfile · docker-compose.yml
└── pyproject.toml
```

## Database
Schema managed by Alembic (`migrations/versions/`). Tables: `organizations`, `users`, `locations`, `markets`,
`storage_sites`, `lots`, `analyses`, `scenarios`, `recommendations`, `explanations`, `outcomes`.
Analyses, scenarios and recommendations are **immutable**: a new analysis is created instead of updating one, which
keeps the prediction → decision → result loop traceable. Every business record is scoped by `organization_id`.

To change the schema: edit `app/db/models/`, then
```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## Integration with the other parts of SALVA
- **Scientific engine** (`salva_core`, `core/` folder): called through `app/services/engines.py`.
  Until it is installed (`pip install -e core`), `/analyze` answers `503 engine-unavailable`.
- **Explanation layer** (`app/llm/service.py`): must expose
  `async def generate(analysis: dict, lang: str) -> dict` returning
  `{"source", "provider", "validated", "summary", "risk", "scenarios", "caveats"}`.
  Free-text lot notes are never sent to it. Until it exists, `/explanation` answers `503 explanation-unavailable`.
- **Reference and demo data** (locations, markets, `demo` organization): loaded by the seed script.
  Without it, requests answer `503 not-seeded`.
- **Front-end**: OpenAPI schema at `/openapi.json`.

## Third-party services
- [Open-Meteo](https://open-meteo.com/) forecast API (temperature; 3 s timeout, 3 h cache, automatic fallback).
- Libraries: FastAPI, Pydantic, SQLAlchemy, Alembic, psycopg, httpx, PyJWT, argon2-cffi, Uvicorn.

## License
MIT.
