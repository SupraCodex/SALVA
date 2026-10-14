# SALVA — Spoilage-Aware Logistics & Value Allocation

Decision support for perishable produce in transit. From a handful of inputs about a lot of
tomatoes, SALVA estimates how much commercial value is likely to be lost before sale, simulates
the realistic decisions (continue, store, reroute to another market, sell locally, or split the
lot), recommends the one that recovers the most value with its uncertainty, and explains the
result in plain French or English without being able to invent a number.

> **Model-based estimate, not validated on field data.** Training data are synthetic (generated
> by a kinetic model) and parameters are literature ranges or assumptions. See
> [docs/model-card.md](docs/model-card.md).

Built for the Devpost hackathon *Build With AI: Basics* by the SupraCodex team.

## What it does

1. **Lot entry** (8 inputs): product, quantity, harvest time, maturity, packaging, departure,
   destination market, planned arrival and delay. Weather along the route (Open-Meteo), route
   distance and duration, and the reference price are filled in automatically, each value
   labelled with its source.
2. **Risk**: likely loss of value as a range (P10-P90) with a central value, a risk level, the
   main contributing factors and an estimated remaining shelf life. Analyses can be replayed at a
   past date.
3. **Decisions**: every feasible option is simulated 2,000 times; unavailable options keep their
   reason. Results are compared on net value in FCFA with their range and the probability of
   being the best option. An optimized split respects storage capacity and market absorption.
   Assumptions (prices, absorption, costs, storage duration) can be edited and the simulation
   rerun; a temperature x delay grid shows where the recommendation would change.
4. **Recommendation and explanation**: the best option for the chosen risk profile, its
   confidence, an explicit "no clear winner" or "least bad option" when relevant, and a checked
   explanation (template by default; Gemini or an OpenAI-compatible model if configured, with
   every number verified against the computed facts).
5. **Questions**: ask about the analysis in plain words. "What if" questions on the delay,
   temperature, packaging or maturity are run through the simulation engine (nothing is saved);
   questions on the risk, the recommendation and its reasons are answered from the stored
   results. The question is never sent to a language model.
6. **Follow-up**: record the decision taken and the real result; history per lot.

Also: organizations with administrator and operator roles, storage sites and the
organization's own market prices and absorption, an assumptions page
listing every parameter with its source and the known limits, French and English interface,
usable on a 360 px wide phone.

## Quick start

```bash
cp .env.example .env              # set JWT_SECRET; SEED_DEMO=true for the demo workspace
docker compose up --build         # http://localhost:8000
```

Without Docker (Python 3.11+, Node 20+, PostgreSQL 16): see [docs/runbook.md](docs/runbook.md)
(`make install`, `make demo`, `make run`).

Online, for free (Render + Neon): [docs/deployment.md](docs/deployment.md).

Demo walkthrough and video plan: [docs/demo-script.md](docs/demo-script.md).

## Repository layout

| Path | Content |
|---|---|
| `core/` | Pure Python science library: kinetics, features, loss models, Monte Carlo simulation, allocation, recommendation, sensitivity |
| `backend/` | FastAPI application, PostgreSQL models and migrations, enrichment, explanation layer, tests |
| `frontend/` | React + TypeScript interface (esbuild), served by the backend |
| `ml/` | Offline pipeline: synthetic data, validation, training, evaluation with a GO/NO-GO gate, packaging |
| `data/reference/` | Product parameters, locations, markets, distances (with sources and assumption notes) |
| `e2e/` | Browser scenarios (Playwright) |
| `docs/` | Architecture, model card, security, runbook, decisions, requirements traceability, hackathon rules, and the team's design document (`docs/design/`, French, revision 1.1) |
| `devpost/` | Skill Pack planning documents (scope, PRD, spec) |

## Quality

- Tests: `make test` (core, ml, backend on PostgreSQL, frontend unit tests) and `make e2e`
  (browser scenarios against a running server).
- CI (`.github/workflows/ci.yml`): lint and types, all test suites, frontend build, browser
  scenarios on PostgreSQL, secret scan of the history and dependency audit.
- Security measures and known gaps: [docs/security.md](docs/security.md).

## Limits

- No field validation yet; the validation plan is in the model card.
- One product (tomato) and one corridor (West region to Douala and Yaounde) in the reference data.
- The truck's live position is unknown: detours are computed from the departure place.
- Live calls to weather, routing and language-model services depend on network access and keys;
  everything degrades to labelled defaults or the template explanation.

## Hackathon compliance

Rules checked on the official page: [docs/hackathon-rules.md](docs/hackathon-rules.md). The
project was started during the submission period (first commit 8 October 2026). Third-party
components are open-source libraries used under their licenses (see each package manifest);
external services: Open-Meteo (weather), optionally OSRM (routing) and Google Gemini or an
OpenAI-compatible API (explanations).

## License

[MIT](LICENSE)
