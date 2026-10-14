# Architecture

SALVA is a modular monolith: one deployable application (API + web interface) built on a pure
Python science library, plus an offline training pipeline.

```
                 browser (React SPA, fr/en)
                        |  HTTPS, JSON, problem+json errors
                        v
 +------------------- backend/ (FastAPI) ---------------------+
 | api/v1   auth, lots, analyses, simulations, explanations,   |
 |          reference data, admin, health                      |
 | services enrichment -> analysis -> simulation ->            |
 |          recommendation -> explanation -> outcomes          |
 | llm/     providers (template | gemini | openai-compatible)  |
 |          + validator (numbers, wording, decision, language) |
 | integrations  Open-Meteo weather, distances table / OSRM    |
 +------------------------------+------------------------------+
                                | imports (no network)
                                v
 +---------------- core/salva_core (pure Python) --------------+
 | kinetics, features, loss models (kinetic | LightGBM),       |
 | Monte Carlo simulation, economics, LP allocation (split),   |
 | recommendation policy, risk levels, sensitivity             |
 +--------------------------------------------------------------+
            ^ same feature code                 |
            |                                   v
   ml/ (offline): generate -> validate -> split -> train ->
   evaluate (GO/NO-GO) -> package -> register (ml/artifacts/active.json)

 PostgreSQL: organizations, users, refresh tokens, locations, markets, storage sites,
 lots, analyses, simulation runs, scenarios, recommendations, explanations, outcomes,
 audit log (Alembic migrations).
```

## Request path of the core journey

1. `POST /api/v1/lots/enrichment-preview` while the form is filled: weather (Open-Meteo,
   3 h cache, multi-point along the route), route distance and duration (distances table,
   optional OSRM, otherwise a haversine x road factor estimate labelled as an assumption),
   reference price.
2. `POST /api/v1/lots` then `POST /api/v1/lots/{id}/analyses`: the lot is turned into features
   by `salva_core.features` (the function used to generate training data), the production loss
   model returns P10/P50/P90, the factor contributions and a shelf-life estimate. Every input is
   stored with its source.
3. `POST /api/v1/analyses/{id}/simulations`: candidate options are built (continue, sell
   locally, reroute to other markets, store at an organization storage site, optimized split),
   unavailable ones keep their reason, each option is simulated with common random numbers
   (2,000 draws, fixed seed), the split is solved as a linear programme, and the
   recommendation policy ranks them for the chosen risk profile. User overrides of
   assumptions are recorded and flagged.
4. `POST /api/v1/recommendations/{id}/explanations`: facts are extracted from the stored
   results; the configured provider writes a text; the validator rejects any number absent
   from the facts, forbidden certainty wording, a wrong recommended option, the wrong language
   or markup. A template explanation is always computed and used whenever the provider is
   absent, fails or is rejected.
5. `POST /api/v1/lots/{id}/outcomes`: the decision taken and later the real result.

## Why this shape

- Numbers come only from deterministic or statistical engines; the language model is outside
  the critical path (design document, section 1).
- One process keeps deployment and debugging simple for a small team; `core/` has no web,
  database or network dependency, so it is tested in isolation and reused by `ml/`.
- The interface is served by the API from `frontend/dist`, so one origin, one cookie scope
  and a strict Content Security Policy (`script-src 'self'`).

## Model registry

`ml/artifacts/active.json` names the production model. A LightGBM package becomes production
only with a `LIGHTGBM GO` verdict and an explicit `--promote`. The current verdict is NO-GO
(see `docs/model-card.md`), so the kinetic model serves every analysis and the LightGBM
package is listed as experimental.
