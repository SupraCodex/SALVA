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
| FR-18 | Could | Ask a question about the analysis | **Not done** | - | - |
| FR-19 | Could | Sensitivity (switching thresholds) | Done | `/simulations/{id}/sensitivity`, grid | core sensitivity tests, manual browser check |
| FR-20 | Should | Admin manages storage sites, markets and users | **Partial**: storage sites and users; markets are shared reference data edited in `data/reference/markets.csv`, overridable per simulation | `api/v1/reference.py`, `api/v1/admin.py`, `pages/Admin.tsx` | `integration/test_auth.py`, `security/test_security.py` |
| FR-21 | Must | Authentication and organization isolation | Done | `security.py`, `deps.py`, services | `security/test_security.py`, `integration/test_auth.py` |
| FR-22 | Must | Permanent "model-based estimate, not a guarantee" notice with link to assumptions | Done | `Disclaimer` in the layout, `pages/Assumptions.tsx` | e2e nominal |

Verified in this repository state: core, ml and backend test suites, frontend type check and
unit tests, six browser scenarios against a local server with PostgreSQL. Live calls to
Open-Meteo, OSRM, Gemini or an OpenAI-compatible service were **not** exercised (the build
environment has no access to them); their clients are tested with mocked HTTP responses.
