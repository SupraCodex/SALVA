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

## Additive input clarifications in `contracts.Option`

| Field | Core meaning | Integration note |
| --- | --- | --- |
| `cost` | Variable cost, FCFA per physical kg | Previously unit-unspecified; confirm with backend before supplying values. |
| `kg` | Maximum physical throughput of this route | For storage, effective throughput is the minimum of route and site capacity. |
| `storage_site_id` | Optional id grouping routes through the same site | Omitted ids are treated as distinct sites. |
| `storage_capacity_kg` | Total capacity of the identified site | If the same site occurs on multiple Options, provide the same value for all. |

These fields were appended with defaults, so existing positional Option constructors remain
valid. They are nevertheless a contract change and are not considered accepted by P3 until
reviewed.

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

## Open contract gap: shelf-life discouragement

RM-4 refers to remaining shelf-life P50, but `LossModel` currently exposes only a loss
fraction at specified conditions. There is no validated mapping from that fraction to
remaining hours or a universal reject threshold. Core therefore does not invent one.
A future extension should define the shelf-life threshold and the producer/consumer for the
result; until then a validated upstream policy may set `ScenarioResult.discouraged=True`.
