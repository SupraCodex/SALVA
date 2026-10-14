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
| `extra_h` | Additional transit/detour hours | For a legacy storage Option with `hold_h=None`, this is still interpreted as the storage hold. |
| `hold_h` | Explicit storage hold duration in hours | New storage Options should set this field; it is excluded from stochastic transit multipliers. |
| `temp_offset` | Storage temperature adjustment in °C | Set from `ProductParams.storage_offset(storage_mode)`; it affects only the storage phase. |
| `transit_saving_h` | Planned transit hours avoided by this route (a market closer than the planned destination) | Non-negative. The route's remaining transit is `max(lot.delay_h, lot.remaining_h - transit_saving_h)`: the delay already incurred is never removed. Used by the backend for `sell_local` and for reroutes to closer markets. |

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

## Storage exposure and feature schema v2

The feature schema is now version `2.0.0` because it includes `hold_h`. Historical age,
future transit and a controlled storage hold are separate phases: weather-temperature and
transit-duration shocks apply only to future transit; a storage `temp_offset` applies only to
`hold_h`; the storage hold is not multiplied by the transit-duration shock. For backward
compatibility, an old `is_store=True` Option that leaves `hold_h=None` continues to interpret
`extra_h` as the hold. New callers should use `extra_h` for detour and `hold_h` for storage.

The kinetic reference integrates the Q10 decay factor over those phases (and over the daily
temperature cycle for historical/transit exposure) rather than applying a storage offset to
the lot's entire age and route. Reported mean temperature and degree-hours are phase weighted;
`temp_max_c` is the maximum over phases with non-zero duration. Storage hold temperature is
treated as controlled/stable, with no weather-driven diurnal amplitude. This is an explicit
model assumption pending site-level temperature time series. Since `hold_h` changes the ML
schema hash, artifacts trained against feature schema 1.x are rejected at load time and must
be regenerated/evaluated before deployment.

`Lot` does not currently carry observed historical temperature series. Until that upstream
contract is available, the historical-age phase uses the supplied nominal air/packaging
temperature as a proxy, without applying the future weather shock. This is a modeling
assumption, not a claim that past conditions were measured.

`storage_mode` is normalized to `none` when `hold_h` is zero, so a category alone cannot
alter the model prediction without a storage exposure. The deterministic explanation factor
`storage` compares against a no-hold/no-storage counterfactual; as with other factors, it is
an attribution of model behavior, not proof of biological causality.

## Chilling injury

The kinetic path and the LightGBM adapter apply a common post-model chilling penalty to
retained value. Core accumulates temperature-weighted cold exposure separately across the
historical-age proxy, future transit and controlled storage hold. The historical phase uses
the nominal air/packaging temperature because `Lot` does not contain an observed cold-chain
history. Product parameters provide maturity-specific lower-temperature boundaries and
onset doses. The green/breaker 10 °C boundary and the short-term 7 °C firm-ripe boundary
are operational anchors drawn from the [UC Davis tomato postharvest guidance](https://postharvest.ucdavis.edu/produce-facts-sheets/tomato),
not cultivar-specific injury thresholds calibrated by this project. [David et al. (2022)]
(https://pmc.ncbi.nlm.nih.gov/articles/PMC9493348/) support the concern about biological
variation: their 148-line population showed markedly different chilling tolerance after
exposure to 1.5 °C. That paper does not validate SALVA's numerical threshold or loss dose
curve. The evidence and its transfer limits are documented in
[`docs/scientific_basis.md`](docs/scientific_basis.md).

The equivalent-hour temperature scale is an initial dose-model assumption selected to map
roughly seven days at 5 °C to fourteen days at 10 °C. The post-onset loss rate is **not** an
experimental or FCFA conversion: the cited studies establish cumulative, maturity-dependent
injury but do not provide a universal economic penalty. Its versioned value in
`data/reference/products.yaml` must be calibrated against cultivar, maturity, grade and
outcome data before operational claims are made. The resulting injury is exposed as the
deterministic `chilling` explanation factor and composes multiplicatively with other loss.

Packaged LightGBM models must declare `loss_includes_chilling_penalty` in `metadata.json`.
Set it to `false` when the artifact predicts loss before the common core adjustment, or to
`true` only when its training target already includes the exact same configured adjustment;
this declaration prevents silent double counting. Older artifacts without the declaration
are rejected by the loader and must be reviewed/repackaged.

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

## Market-specific uncertainty and legacy compatibility

`draw(n, seed, market_ids=...)` populates independent one-dimensional vectors in
`Shocks.price_by_market` and `Shocks.absorb_by_market`. A market's factors are reused by
every option routed to that market within each draw, while distinct market ids receive
independent factors. This is required for the design's independent-market assumption without
breaking the stable legacy `Shocks.price` / `Shocks.absorb` vectors. Hand-built historical
`Shocks` bundles may leave either mapping `None`; in that compatibility mode, the shared
legacy vector is used for all markets. New production callers should use `draw(...,
market_ids={...})` or supply the per-market maps explicitly. When maps are present but omit
a particular market id, that market also uses the legacy shared vector.

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

`relative_hypothesis_parameter_paths(params, model=model)` enumerates non-zero numeric
product parameters marked `source: assumption` whose default ±30% variants remain within
the configured product domain and are supported by the supplied model adapter. Without
`model`, it lists product-level candidates. It excludes literature-sourced parameters and zero baselines
(for which a percentage change is undefined). `analyze_parameter_sensitivity` includes
P10/P50/P90-based scenario risk levels in its output as well as the recommendation so RM-5
changes are not hidden when risk thresholds are varied. Neither API calibrates model values
or substitutes for independent field validation.

For a product parameter that must enter the loss model, an adapter must implement both
`supports_parameter_sensitivity(path) -> bool` and `with_params(params)`. Sensitivity is
rejected when the adapter cannot demonstrate an inference pathway. The LightGBM adapter
supports only parameters that alter its feature inputs, shelf-life test, or common chilling
adjustment; varying a kinetic or grading coefficient that would require fitting new trees is
rejected with an explicit error. Price-tier `delta` and RM-5 thresholds are applied by the
economics/risk layers and do not require a model rebind.
