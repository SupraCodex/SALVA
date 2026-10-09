# SALVA core — simulation, allocation, recommendation

This package implements only the Python decision engine. It does not contain the API, UI,
model-training pipeline, LLM explanation service, or persistence layer.

## Public entry points

```python
from salva_core.simulation import SimulationEngine, draw, optimize, run_all
from salva_core.recommendation import Policy, recommend

shocks = draw(n=2_000, seed=42)
results = run_all(loss_model, lot, options, shocks, product_params)
choice = recommend(results, Policy(lam=0.5))
assert choice.best_id is None or choice.best_id in {r.id for r in results}
```

The P3 adapter signatures are deliberately stable:

- `run_all(model, lot, options, shocks, params)` returns scenario-result objects. Each exposes
  `id`, `net_draws`, `net_p10`, `net_p50`, `net_p90`, `prob_best`, `feasible`, and
  `discouraged`.
- `recommend(results, policy)` returns a recommendation with `best_id` and
  `rationale_codes`.

`SimulationEngine(model, params).run(lot, options, n_draws=2_000, seed=42)` is the
convenience API that creates the shocks and calls the same adapter.

## What is calculated

1. **Common random numbers:** one seeded shock bundle is reused for every route. Production
   runs use at least 1,000 draws (2,000 by default); a run is deterministic for a given
   model, lot, options, parameter file, draw count, and seed.
2. **Loss and recoverable quantity:** the selected `LossModel.sample_loss(features, u)` is
   the only source of loss draws. Recoverable kg are full-price-equivalent kg, not a claim
   that all those kg can be sold at full price.
3. **Market economics:** quantities routed to the same market are aggregated before the
   full-price absorption cap is applied. Excess recoverable quantity receives the product's
   `delta` discount. Variable route cost is `Option.cost` in FCFA per physical kg.
4. **Allocation:** the LP maximizes a linear expected-value approximation using Monte Carlo
   mean retained value fractions over full-price and discounted-surplus tiers, with one
   market constraint per market, per-route throughput limits, and shared capacity per
   storage site. A zero-revenue discard variable ensures that every physical kg is accounted
   for; discarded quantity is returned explicitly. The fixed plan is then evaluated across
   the shared draws and reported with P10/P50/P90.
5. **Decision:** the policy score is `net P50 - lam * (net P50 - net P10)`. When the score
   gap is below materiality and the Monte Carlo best probability is low, the engine returns
   `best_id=None` rather than inventing a winner. Reason codes are deterministic; prose is
   left to the application layer. `HIGH_TEMP` uses the nominal effective mean product
   temperature (air + packaging + storage offset), strictly above 30 °C, not one random draw.
6. **Risk and shelf life:** feasible results expose a product-configured risk level derived
   from loss P50 and P10-P90 width. Models implementing the optional
   `remaining_shelf_life_p50_h` contract can mark a route `discouraged` when nominal transit
   exceeds that estimate; discouraged routes are excluded from best-action probabilities and
   optimized allocation. The kinetic implementation labels its threshold as an assumption,
   not a validated expiry guarantee.
7. **Sensitivity:** `analyze_sensitivity` evaluates a temperature/delay grid through the
   same `run_all` and recommendation code, with one common shock bundle for every cell, and
   reports only actual action boundaries.
8. **Extrapolation:** configured calibration ranges are checked against effective features.
   The kinetic reference keeps physical inputs and reports out-of-range features; LightGBM
   clips at inference and reports the same warnings in predictions and scenario JSON.
9. **Recommendation assumptions:** recommendations expose stable assumption codes for the
   model estimate, product calibration and market-absorption hypothesis.

## Contract notes for P3 / backend

The original `Option` positional fields are unchanged; two optional fields were appended:

- `storage_site_id`: identifies options that consume the same physical storage pool.
- `storage_capacity_kg`: total physical capacity of that pool. If omitted, the route's
  `Option.kg` is used as its site's capacity.

The previously unspecified `Option.cost` unit is now explicit: **FCFA per physical kg**.
These are additive/backward-compatible shape clarifications on the `feat/spectre-core`
branch, but P3/backend should review them before integration. `Option.kg` is the route's
maximum throughput and may exceed the lot quantity; a whole-lot single-action result is
infeasible if that route or its storage site cannot hold the entire lot, while the allocation
LP may still use it for a partial lot.

The `Shocks` contract currently supplies one `price` and one `absorb` vector, shared by all
routes and markets within each draw. This correctly pairs alternatives for common-random-
number comparisons, but it does **not** model independent market-specific prices or demand;
that requires a versioned P3 contract extension, not an implicit shape change here.

## Boundaries and unresolved integration points

- Sensitivity analysis is optional in the product MVP but is implemented as a core API; it is
  not required for the basic simulation/recommendation call path.
- RM-4 is implemented only when the selected model exposes
  `remaining_shelf_life_p50_h(features)`. The kinetic threshold and its temperature-history
  simplification remain assumptions, not a validated expiry guarantee. Adapters without this
  optional capability do not receive an invented shelf-life estimate.
- Multi-period pricing, endogenous price response, multi-lot optimization, fixed-charge
  routing, contracts, payment delays, quality safety decisions, non-tomato products and
  validation against field outcomes are out of scope. Product values and market capacities
  remain assumptions until calibrated.
- The current one-dimensional `Shocks.price` and `Shocks.absorb` vectors are shared across
  markets. Independent market-specific shocks require a reviewed, versioned P3/backend
  contract change; core does not silently reinterpret the existing vectors.
- Extrapolation-warning and recommendation-assumption fields are additive proposals and
  should be reviewed by P3/backend before integration.
- No LLM produces or edits numeric results. The exact simulation arrays and summaries are
  source-of-truth outputs.

## Hackathon submission note

The official Build With AI: Basics rules also require the project-wide `devpost/scope.md`,
`devpost/prd.md`, and `devpost/spec.md` produced through the Learn Skill Pack, plus a public
repository/license and a sub-three-minute demo video. This core-only branch does not claim
to satisfy those team-level submission requirements and does not fabricate those planning
artifacts; the project team must complete and review them separately.

## Verification

Run from the repository root:

```bash
python -m pip install -e "core[dev]"
python -m pytest core/tests -q --cov=salva_core --cov-fail-under=70
ruff format --check core && ruff check core
mypy core/salva_core --ignore-missing-imports
```

The core remains importable as a pure Python package. `scipy.optimize.linprog` uses the
HiGHS backend declared by the package; no network services are called by the engine.

## Engineering guarantees

The engine rejects unknown actions, malformed shock vectors, invalid loss fractions,
inconsistent market metadata, and allocations that exceed a shared storage site. Every
allocation conserves physical mass: routed kilograms plus explicit discard equals the lot
quantity. Counterfactual features apply the same delay invariant as production features,
and quantile interpolation rejects non-monotone probability levels instead of silently
producing a result.

The test suite includes adversarial cases for shared storage capacity, mass conservation,
common random numbers, infeasible whole-lot routes, quantile ordering, negative-value
discard, and deterministic recommendations. These tests are not a scientific validation
claim: the committed product parameters are assumptions pending literature and field
calibration.
