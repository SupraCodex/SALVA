# Core ↔ P3/backend contract review

Status: **implementation proposal on `feat/spectre-core`; requires P3/backend review before
integration**. The branch intentionally does not merge or copy another teammate's branch.

## Stable call shapes

```python
results = run_all(model, lot, options, shocks, params)
choice = recommend(results, policy)
choice.best_id  # id of a selected Option, "optimized_split", or None
```

`run_all` keeps the original five positional arguments and reuses the supplied `Shocks`
without resampling. It returns one `ScenarioResult` per candidate, plus `optimized_split`
when the LP creates a real split or an explicit discard. A candidate is infeasible as a
whole-lot decision if its route or storage capacity is less than `Lot.kg`; it can still
participate in a partial allocation. The backend should render infeasibility and
`NO_CLEAR_WINNER` explicitly rather than replace them with a default action.

`ScenarioResult.as_dict()` exposes `extrapolation_warnings` as feature-name codes. These
identify effective numeric features outside configured calibration ranges. The kinetic
reference keeps the physical feature values; LightGBM clips to the configured ranges before
prediction. Both models preserve P50 and, on an extrapolated row, expand the outer P10/P90
bounds to the physical loss support [0, 1]. The backend should surface a warning instead of
presenting such a prediction as calibrated. Packaged-model `metadata.json` may
override the versioned planning-envelope ranges using the `calibration_ranges` mapping;
malformed metadata is rejected.

`Recommendation.as_dict()` includes the stable `assumptions` codes required by RM-6, in
addition to confidence and rationale. The backend should render those assumptions in the
selected language rather than hiding them in explanatory prose.
When candidates are economically indistinguishable, `best_id` is `None`,
`no_clear_winner` is true, and confidence is `low`; `confidence="none"` is reserved for
the absence of any eligible action, where there is no recommendation to qualify.
`confidence="high"` requires both the configured probability and a material score gap to an
actual second candidate. With exactly one eligible scenario, the gap is `None` (not an
invented 100% gap) and confidence cannot be `high` solely by construction.
`run_all` attaches a shared `lot_reference_value_fcfa = lot.kg * max(candidate market price)`
before losses, discount, or costs. Unless `Policy.reference_value_fcfa` overrides it, the
relative score gap is measured against that nominal lot reference, as required by the default
3% materiality rule. Legacy results without this field retain the score-relative fallback.

## Additive input clarifications in `contracts.Option`

| Field | Core meaning | Integration note |
| --- | --- | --- |
| `cost` | Variable cost, FCFA per physical kg | Previously unit-unspecified; confirm with backend before supplying values. |
| `kg` | Maximum physical throughput of this route | For storage, effective throughput is the minimum of route and site capacity. |
| `storage_site_id` | Optional id grouping routes through the same site | Omitted ids are treated as distinct sites. |
| `storage_capacity_kg` | Free physical capacity available to this simulation, after occupied/reserved stock | If the same site occurs on multiple Options, provide the same available value for all; core has no inventory ledger and cannot derive free capacity from nominal site capacity. |

These fields were appended with defaults, so existing positional Option constructors remain
valid. They are nevertheless a contract change and are not considered accepted by P3 until
reviewed.

For RM-2, this value must be the *free* capacity available to the current lot, not a site's
nominal rated capacity. P2/backend must subtract already occupied or reserved stock; if that
cannot be determined, it must not offer the storage action as feasible. When omitted for a
standalone storage option, `Option.kg` is treated as its available capacity.

`Market.absorb_kg` is a required finite input, not an optional value. The design requires
preloaded, modifiable market defaults and an explicit assumption label when the market has
no measured capacity. No numeric default or market reference file is present in this core
branch, so core deliberately does not invent one: P2/backend or the project reference-data
owner must resolve the per-market default and include the assumption in the user-visible
inputs before calling `run_all`. Passing `None` is invalid.

## Economic invariants

- Loss is a fraction in [0, 1]; higher common `u` is a higher/equal loss quantile.
- Every scenario reuses the same draws; all vectors must have the same length.
- `recoverable_kg = physical_kg * (1 - loss)` is full-price-equivalent kg.
- For a given market and draw, the full-price tier is bounded by the market's absorption;
  any excess is valued using product `delta`. Routes to one market share this cap.
- Allocation conserves physical mass: `sum(route kg) + discarded_kg == Lot.kg`.
- Allocation uses the Monte Carlo mean retained-value fraction as the LP coefficient; Monte
  Carlo results then evaluate that fixed decision across the common shocks. It is not a
  per-draw clairvoyant optimizer.
- Recommendation is risk-adjusted after simulation, and never changes the underlying
  financial outputs.

## Open contract gap: market-specific uncertainty

The current `Shocks.price` and `Shocks.absorb` are one-dimensional shared vectors. Core does
not reinterpret them as two-dimensional matrices because that would be an undocumented
breaking change. Consequently market prices/demand are perfectly co-moving under these
shocks, contrary to the design document's independent-market assumption. A future versioned
contract should define stable market ids and per-market shock columns/maps, with tests and
review from P3.

## Shelf-life and risk contracts

RM-4 is implemented as an optional model capability:

- a model may expose `remaining_shelf_life_p50_h(features) -> scalar hours`;
- `run_all` compares that estimate with the nominal route transit and sets
  `ScenarioResult.discouraged=True` plus `discouraged_reason=SHELF_LIFE_P50_EXCEEDED`;
- discouraged routes remain measurable but are excluded from best-action probabilities,
  recommendation and optimized allocation;
- the kinetic model implements this capability using the product's explicit
  `shelf_life_loss_threshold`. That threshold is currently an assumption and must be
  calibrated before it is presented as an expiry guarantee.

RM-5 is implemented by `salva_core.risk.classify_risk`: product-configured P50-loss and
P10–P90-width thresholds are combined conservatively, taking the higher resulting level.
The result is exposed as `ScenarioResult.risk_level` and is calculated from the same draws
used for the economic result.

`analyze_sensitivity` is an optional grid API over temperature and delay. It calls the
production simulation and recommendation paths for every grid cell and reports actual
action transitions; it does not fit a second surrogate model.
Its returned axes are sorted ascending, so each transition follows increasing temperature
or delay regardless of the caller's input order.
