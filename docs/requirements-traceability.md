# Requirements traceability (product level)

Functional requirements of the design document (section on functional requirements) mapped to
the code and the tests that exercise them (backend test paths are under `backend/tests/`). Core-library details: `core-requirements-traceability.md`.

| Id | Priority | Requirement (summary) | Status | Implementation | Tests |
|---|---|---|---|---|---|
| FR-01 | Must | Create a lot in under two minutes | Done | `api/v1/lots.py`, `pages/NewLot.tsx` (example prefill, saved draft) | `integration/test_lots_analysis.py`, e2e nominal |
| FR-02 | Must | Validate every field, readable errors | Done | `schemas/lot.py`, problem+json, `fieldErrors` | `integration/test_lots_analysis.py`, `frontend/tests/i18n.test.ts` |
| FR-03 | Must | Automatic weather, route duration, reference price; manual fallback | Done | `integrations/weather.py`, `integrations/routing.py`, enrichment preview | `unit/test_integrations.py` (mocked HTTP), e2e weather fallback |
| FR-04 | Must | Derived variables (age, exposure, degree-hours) | Done | `core/salva_core/features.py` | core feature tests |
| FR-05 | Must | Loss P10/P50/P90 and risk level | Done | `services/analysis.py`, kinetic model | core tests, `integration/test_lots_analysis.py`, e2e nominal |
| FR-06 | Must | Main factors of the estimate | Done | `loss_model/factors.py`, `FactorList` | `integration/test_lots_analysis.py` |
| FR-07 | Must | Feasible actions only, with reasons for the others | Done | `services/simulation.py build_plan` | `integration/test_simulation.py` |
| FR-08 | Must | Monte Carlo simulation of each action | Done | `core/salva_core/simulation` | core simulation tests |
| FR-09 | Must | Optimized allocation (split) under capacity and absorption | Done | `simulation/allocation.py` (linear programme) | core allocation tests |
| FR-10 | Must | Recommendation, confidence, no clear winner, least bad | Done | `core/salva_core/recommendation` | core recommendation tests, `integration/test_simulation.py` |
| FR-11 | Must | Structured explanation | Done | `llm/`, `services/explanation.py` | `unit/test_llm_explain.py`, `integration/test_explanation_outcomes.py` |
| FR-12 | Must | Explanation cannot invent a number; template fallback | Done | `llm/validator.py` | `unit/test_llm_validator.py`, e2e (explanation contains the banner value) |
| FR-13 | Should | French / English interface and explanations | Done | `lib/messages.ts`, `lang` on explanations | dictionary parity test |
| FR-14 | Should | History of lots and analyses | Done | `/lots/{id}/history`, `pages/History.tsx` | `integration/test_explanation_outcomes.py`, e2e outcome |
| FR-15 | Should | Record decision then real result | Done | `/lots/{id}/outcomes`, `OutcomeForms` | `integration/test_explanation_outcomes.py`, e2e outcome |
| FR-16 | Should | Replay an analysis at a chosen date | Done | `analysis_at` on analyses, replay control | `integration/test_lots_analysis.py`, manual browser check |
| FR-17 | Should | Edit price, absorption, costs and rerun | Done | `SimulationAssumptionsIn`, assumptions editor | `integration/test_simulation.py`, e2e override |
| FR-18 | Could | Ask a question about the analysis, answered only from its facts | Done: "what if" on delay, temperature, packaging or maturity is simulated without saving; risk, recommendation, reasons, uncertainty and assumptions answered from stored results; other questions declined | `services/questions.py`, `components/AskPanel.tsx` | `integration/test_questions_markets.py`, e2e question |
| FR-19 | Could | Sensitivity (switching thresholds) | Done | `/simulations/{id}/sensitivity`, grid | core sensitivity tests, manual browser check |
| FR-20 | Should | Admin manages storage sites, markets and users | Done: storage sites, users, and per-organization market price and absorption (reference values stay shared) | `api/v1/reference.py`, `api/v1/admin.py`, `pages/Admin.tsx` | `integration/test_questions_markets.py`, `integration/test_auth.py`, `security/test_security.py`, e2e market value |
| FR-21 | Must | Authentication and organization isolation | Done | `security.py`, `deps.py`, services | `security/test_security.py`, `integration/test_auth.py` |
| FR-22 | Must | Permanent "model-based estimate, not a guarantee" notice with link to assumptions | Done | `Disclaimer` in the layout, `pages/Assumptions.tsx` | e2e nominal |

## Non-functional requirements

| Id | Requirement | Status | Evidence |
|---|---|---|---|
| NFR-01 | Analysis + simulation under 3 s | Done | simulation about 40-50 ms, analysis under 0.2 s locally; latency test in `integration/test_simulation.py` |
| NFR-02 | Useful first page fast on 3G | Done | one gzip-compressed bundle (about 95 KB of JavaScript), cached for a year by content hash, no external font or CDN |
| NFR-03 | Usable without the language model | Done | template explanation by default; e2e runs with no provider |
| NFR-04 | Manual entry when weather or routing fail | Done | temperature field and planned arrival; e2e weather fallback |
| NFR-05 | Same inputs, seed and model give the same outputs | Done | core reproducibility tests, `test_what_if_is_deterministic...` |
| NFR-06 | Each analysis stores model version, inputs, assumptions, seed | Done | `analyses` and `simulation_runs` columns |
| NFR-07 | Lint, types and formatting in CI | Done | ruff, mypy, tsc in `.github/workflows/ci.yml` |
| NFR-08 | Coverage at least 70 % core, 60 % backend | Done | `--cov-fail-under` gates in CI |
| NFR-09 | Lot created in 2 minutes or less | Partly verified | 8 required inputs and example prefill; no test with 5 users yet |
| NFR-10 | AA contrast, keyboard, explicit labels | Done (manual check) | palette ratios at least 4.5:1, visible focus, labelled fields, icons with risk colours; no automated axe audit |
| NFR-11 | Usable from 360 to 1440 px | Done | e2e at 360 px without horizontal scroll, screenshots at 1280 px |
| NFR-12 | Externalised French and English texts | Done | `lib/messages.ts`, key parity test |
| NFR-13 | `docker compose up` locally | Done | Docker smoke test job in CI |
| NFR-14 | Structured JSON logs with request id | Done | `app/logging.py`, `X-Request-ID` header |
| NFR-15 | Free or very low cost | Done | PostgreSQL + one container; Open-Meteo without key; language model optional |

Verified in this repository state: core, ml and backend test suites, frontend type check and
unit tests, eight browser scenarios against a local server with PostgreSQL. Live calls to
Open-Meteo, OSRM, Gemini or an OpenAI-compatible service were **not** exercised (the build
environment has no access to them); their clients are tested with mocked HTTP responses.
