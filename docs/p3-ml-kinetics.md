# P3 — Kinetic model, features, synthetic data and LightGBM surrogate

Owner: P3 (ML + kinetics). Scope: `core/salva_core/{kinetics,features,params}.py`,
`core/salva_core/loss_model/`, `data/reference/products.yaml`, `ml/`.

> **DATA TYPE = SYNTHETIC. GENERATOR = KINETIC MODEL.** Every training label is computed
> by the kinetic model. No number in this folder is a field observation. **Real-world
> validation: NOT PERFORMED.** All constants in `products.yaml` are *assumptions* to be
> calibrated (literature, interviews); none has a verified citation yet.

## 1. Kinetic model (`core/salva_core/kinetics.py`)

For a lot with effective mean product temperature `T`, daily half-amplitude `A = T_max − T`
and exposure `H` hours:

```
k = k_ref · q10^((T − T_ref)/10) · I0(A·ln(q10)/10) · m_mat · k_lot
Q = exp(−k·H)                                  mean quality, in (0, 1]
q_i = Q · exp(σ_h · ε), ε ~ N(0,1)             individual fruit
grade A/B/C/D by thresholds, price multipliers (1, 0.6, 0.3, 0)
loss = 1 − value_fraction(Q) · (1 − pack_damage)            in [0, 1]
```

* `I0` (modified Bessel) is the exact daily average of the Q10 law over a sinusoidal day:
  temperature swings accelerate decay at equal mean temperature.
* `k_lot = exp(σ_lot · ndtri(u))`, `u ~ U(0,1)`: lot-to-lot variability.
* The loss is non-decreasing in `u`, so the loss quantile of level `p` is *exactly*
  `sample_loss(f, p)`: **P10/P50/P90 are the losses at u = 0.1/0.5/0.9** — one distribution,
  never crossing.
* Functions are pure, typed, vectorised; no network, DB, FastAPI or LLM.

**Known simplifications** (also in `model-card` input): constant mean temperature plus a
sinusoidal day; no humidity, ethylene or vibration; chilling injury is a configured
dose-response penalty below maturity-specific thresholds (labels include it since generator
2.0.0), not a fitted law, so `cold_room` results stay assumption-driven; a fresh lot already has ≈ 3% grading loss + packaging
damage because of `σ_h`; `delay_h` acts only through `remaining_transit_h`.

## 2. Parameters (`data/reference/products.yaml`)

Each parameter has `value, unit, description, source, note`; `source ∈ {literature,
interview, assumption}` and `literature` requires a `reference`. `core/salva_core/params.py`
rejects incomplete entries and inconsistent values (ordering of maturity/grades, bounds).
Currently every source is `assumption` except the chilling thresholds (`literature`, UC Davis
postharvest fact sheet). Do not change a source without a real reference.

## 3. Features (`core/salva_core/features.py`)

`assemble(...)` is the only code that builds features; `build(lot, option, shocks, p)` wraps
it for the simulation, `ml/generate.py` calls `assemble` directly → **identical logic in
training and production**.

| feature | unit | meaning |
|---|---|---|
| `age_h` | h | hours since harvest |
| `temp_mean_c` | °C | effective product temp = air + packaging Δ + storage offset + shock |
| `temp_max_c` | °C | `temp_mean_c` + daily half-amplitude |
| `degree_hours_above_ref` | °C·h | `max(temp_mean − T_ref, 0) · exposure_h` |
| `remaining_transit_h` | h | `(remaining + extra) · transit_factor`, **includes** the delay |
| `delay_h` | h | delay vs plan (informational; already inside remaining) |
| `exposure_h` | h | `age_h + remaining_transit_h` |
| `maturity`, `packaging`, `storage_mode` | cat. | integer codes in `features.py` (`FEATURE_VERSION`) |

`feature_schema()` / `schema_hash()` are stored in every model package; loading a model with
another schema raises `ModelSchemaMismatch`.

## 4. Synthetic data (`ml/generate.py`)

Data are organised in **lots** (default 4 000 lots × 40 rows = 160 000 rows). A lot fixes
maturity, packaging, base air temperature, daily amplitude and the hidden `u`; rows are
different observed states (Latin-hypercube sampling of age, planned transit, delay, shocks,
optional storage). Hidden columns `hidden_u`, `hidden_mean_quality` are stored for
verification and are **never features**. Dataset = f(seed, `ml/params/tomato.yaml`,
`products.yaml`, generator version); `metadata.json` records seed, versions, hashes and
`DATA_TYPE=SYNTHETIC`. Common random numbers: the same `u` (and shocks) are used for every
action in the simulation (`sample_loss(f, u)`).

## 5. Pipeline and commands

```bash
pip install -e core && pip install -r ml/requirements.txt
python -m ml.generate --seed 42                          # -> ml/artifacts/datasets/<id>/
python -m ml.validate --dataset ml/artifacts/datasets/<id>
python -m ml.split    --dataset ml/artifacts/datasets/<id>   # -> ml/artifacts/splits/<dir>/
python -m ml.baseline --split ml/artifacts/splits/<dir>      # kinetic baseline FIRST
python -m ml.train    --split ml/artifacts/splits/<dir>      # -> ml/artifacts/runs/<version>/
python -m ml.evaluate --run ml/artifacts/runs/<version> --split ml/artifacts/splits/<dir>
python -m ml.package  --run ml/artifacts/runs/<version> --report ml/reports/<version>
python -m ml.register --package ml/artifacts/models/<version> --report ml/reports/<version>
ruff check . && pytest -q
```

* **Split** (`ml/split.py`): by lot (rows of a lot are correlated), 65/12.5/12.5/10 % of
  lots for train/val/test/extrapolation; rows with `temp_mean_c > 34` or `age_h > 96` never
  appear in train/val/test (kept only in extrapolation lots). Test is sealed.
* **Leakage guards:** hidden columns forbidden as features (`assert_no_forbidden_features`),
  labels re-computed from `kinetics.py` during validation (max error must be 0), no lot in two
  splits, feature code shared with production.

## 6. LightGBM (`ml/train.py`, `core/salva_core/loss_model/lgbm_model.py`)

Seven quantile models (5, 10, 25, 50, 75, 90, 95 %), sorted per row (no crossing), clipped
to [0,1]; `sample_loss` interpolates the quantile curve (flat tails beyond 5%/95%).
**Deviation from the coding guide:** LightGBM refuses `monotone_constraints` with its native
quantile objective. The default mode therefore trains a **custom pinball objective** (hessian
= 1) with monotone constraints on temperature, durations, amplitude and maturity
(`lightgbm.mode: pinball_custom_monotone`); `native_quantile` remains available as an
unconstrained ablation. `predict()` evaluates only the P10/P50/P90 models (same results the
registered latency criterion measures); `sample_loss` uses all seven.
Explainability: `loss_model.factors.explain(model, f, params)` — model-agnostic
one-at-a-time counterfactuals (temperature, age, transit, delay, maturity, packaging) in
loss-fraction units, identical for both models; raw TreeSHAP via
`LightGbmLossModel.shap_contributions` (global importance in the report). Factors describe
how the model reasons, not biological causality; the LLM must not add any other factor.

## 7. Go / no-go (18 Oct)

Thresholds are in `ml/params/go_nogo.yaml`, **committed before any model was trained**
(git history, first commit of the branch). `evaluate.py` records the file sha256 and flags the
verdict if it was modified after its commit. All criteria are required:

| criterion | rule |
|---|---|
| P50 fidelity MAE vs kinetic (test) | < 0.03 |
| P10–P90 coverage of realised losses (test) | 0.76 – 0.84 |
| monotonicity violations | 0 |
| recommended-action agreement with kinetic (P1 engines) | ≥ 0.85 — *not evaluable until P1 delivers; counts as failed* |
| latency, 10 000 rows, median | < 300 ms (CPU) |

**Current result: LIGHTGBM NO-GO** (`ml/reports/lgbm-1.0.0-83dd816d-s42/report.md`): the
four other criteria pass, the decision criterion is not evaluable. Production model =
`KineticLossModel`; LightGBM = experimental. Re-run `ml.evaluate` once P1's simulation and
recommendation engines exist; GO is then possible. Honest caveats: coverage 0.769 passes
narrowly (95 % CI [0.739, 0.797] over 500 test lots; the kinetic reference itself scores
0.769, i.e. sampling noise); fidelity degrades outside the training domain (extrapolation
P50 MAE 0.038, max 0.25); latency was measured on a 1-CPU sandbox; a first evaluation
(`ml/reports/<version>/history/`) measured 659 ms before `predict()` was restricted to three models —
thresholds were not touched.

## 8. Using the loss model

```python
from salva_core.loss_model import get_loss_model      # production model, kinetic fallback
from salva_core import features
from salva_core.params import load_product

params = load_product("tomato")
model = get_loss_model()                               # LossModel contract
f = features.build(lot, option, shocks, params)        # P1: one call per action
loss = model.sample_loss(f, shocks.u)                  # (N,) same u for every action
value_fraction = 1.0 - loss
dist = model.predict(f, with_factors=False)            # P10/P50/P90 (floats if 1 row)
```

`SimulationEngine(loss_model=get_loss_model(), ...)` needs nothing else from P3.
`get_loss_model()` never raises because of the ML package: if `ml/artifacts/active.json`
names a missing/incompatible model it logs a warning and returns the kinetic model.

## 9. Contract notes for the team

* **CONTRACT CHANGE REQUIRED — `core/salva_core/contracts.py` (P1 review).** File did not
  exist; P3 created it so work could proceed. Defines `Market, Lot, Option, Shocks,
  ConditionFeatures, LossDistribution, LossModel`. Additions vs the guide: `Lot.delay_h`,
  `Lot.diurnal_amp_c`, `Option.storage_mode`, `Shocks` lives here. Proposed: P1 keeps
  these names; if P1 needs a change, edit this file in a PR reviewed by P3.
* **Storage offsets (P1):** build storage options with
  `temp_offset=params.storage_offset(mode)` and `storage_mode=mode`.
* **`core/pyproject.toml`, `core/salva_core/__init__.py`, `params.py`** were created by P3 for
  the same reason (shared; merge carefully).
* **CI (P4):** ML tests need `pip install -r ml/requirements.txt` (pandas, pyarrow, lightgbm)
  in addition to `pip install -e core`. Proposed change to `ci.yml`; not made by P3.
* **P2:** `from salva_core.loss_model import get_loss_model`; `pip install -e "core[lgbm]"`
  only if LightGBM is ever promoted. Env var `SALVA_ACTIVE_MODEL_PATH` overrides
  `ml/artifacts/active.json`.
* **P1 decision adapter:** `ml/decision_agreement.py` calls
  `salva_core.simulation.uncertainty.draw(n, seed)`, `salva_core.simulation.engine.run_all(model, lot,
  options, shocks, params)` and `salva_core.recommendation.engine.recommend(results, policy)`
  returning an object with `.best_id`. If signatures differ the criterion is reported as
  NOT EVALUATED with the error message.
