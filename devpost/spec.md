---
doc: spec
status: draft
---
<!-- Consolidated from the team's design document and the implemented architecture.
     Review with the Skill Pack's 4-spec skill; set `status: approved` when the team agrees. -->

# SALVA — Technical Spec

## How This Works, In Plain Language
A web page (the interface) talks to one server program (the API). The API stores lots and
results in a database, fetches the weather, and calls a calculation library that knows how
tomatoes lose value with time and heat. That library also simulates each possible decision many
times with random variations, so results come as ranges. A separate, optional language model
only rewrites the computed facts into sentences, and a checker throws its text away if it adds
a number. One server and one library keep the project simple enough for a small team.

## The Core Journey Through the System
User fills the lot form → `POST /api/v1/lots/enrichment-preview` (weather, route, price) → user
submits → `POST /api/v1/lots` then `POST /lots/{id}/analyses` → `core` builds features and the
kinetic model returns P10/P50/P90 → stored and shown on the Risk tab → `POST
/analyses/{id}/simulations` → `core` simulates options and solves the split → recommendation
stored → `POST /recommendations/{id}/explanations` → validated text or template → user records
`POST /lots/{id}/outcomes`. PRD ref: `prd.md > The Core Journey`.

## Stack
- Python 3.11+, FastAPI 0.143, SQLAlchemy 2.1, Alembic, Pydantic 2, PostgreSQL 16
  (https://fastapi.tiangolo.com, https://docs.sqlalchemy.org).
- NumPy and SciPy for the science library; LightGBM 4.6 for the experimental surrogate.
- React 19.2 and TypeScript 6.0 bundled by esbuild 0.28 (https://react.dev).
- Playwright for browser tests.

## Where It Runs and How Someone Tries It
`docker compose up --build` then http://localhost:8000 (see `docs/runbook.md`). A public demo
video under 3 minutes and the public GitHub repository are required for submission; deployment
is optional.

## Look and Feel
Field-office green, ripening colours only for risk, system fonts, ranges drawn as a band with a
central tick, plain sentence-case copy in French and English.

## Components
### core/ (science library)
Kinetics, features, loss models, simulation, allocation, recommendation, sensitivity. No I/O.
PRD ref: `prd.md > Features and Behavior`.
### backend/ (API)
Authentication, organizations, lots, enrichment, analyses, simulations, explanations, outcomes,
administration, health. PRD ref: `prd.md > The Core Journey`.
### frontend/ (interface)
Pages listed in `prd.md > Screens and Layout`.
### ml/ (offline)
Synthetic data generation, training, evaluation with a GO/NO-GO gate, packaging, registry.

## Data Model
Organizations, users, refresh tokens, locations, markets, storage sites, lots, analyses,
simulation runs, scenarios, recommendations, explanations, outcomes, audit log (PostgreSQL,
migration `backend/migrations/versions/0001_initial_schema.py`). Everything persists between
sessions; the access token lives only in memory and is renewed from an HttpOnly cookie.

## File Structure
```
salva/
├── core/            # science library + tests
├── backend/         # FastAPI app, migrations, tests
├── frontend/        # React interface, build script, unit tests
├── ml/              # offline pipeline, reports, packaged models
├── data/reference/  # products.yaml, locations, markets, distances
├── e2e/             # browser scenarios
├── docs/            # architecture, model card, security, runbook, demo script
└── devpost/         # Devpost learning workspace (scope, prd, spec)
```

## External Services and Dependencies
- Open-Meteo forecast API (no key; cached 3 h).
- Optional OSRM-compatible routing service; otherwise a distance table then a labelled estimate.
- Optional Google Gemini or OpenAI-compatible chat API (`LLM_API_KEY`), for explanations only.

## Important Failure Modes
- **Weather service unreachable** → default temperature, labelled as an assumption.
- **Language model unavailable or text rejected** → template explanation.
- **Every route exceeds the shelf life** → least bad option named, heavy losses warned.

## What Was Simplified and Why
- **Kinetic model in production** instead of a learned model: the surrogate fails the
  monotonicity gate. Field data would be needed to do better.
- **In-memory rate limiting** instead of a shared store: one instance is enough for the POC.

## Decisions and Open Issues
See `docs/decisions.md`. Open: field validation, FR-18, market administration.
