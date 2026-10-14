# Model card: SALVA loss-of-value models

> **Data type: synthetic.** Training labels are computed by the kinetic model. No figure on this
> page is a field observation. **Real-world validation: not performed.**

## Intended use

Estimate, for one lot of tomatoes in transit, the fraction of commercial value likely to be lost
by the time it is sold (P10, P50, P90), so that SALVA can compare decisions (continue, store,
reroute, sell locally, split). It is a decision aid. It does **not** say whether food is safe to
eat, and it is not calibrated on Cameroonian field data.

## Models

| | Kinetic model (production) | LightGBM surrogate (experimental) |
|---|---|---|
| Version | `kinetic-2.0.0+<params hash>` | `lgbm-2.0.0-8795c6c2-s42` |
| What it is | Q10 decay law with a sinusoidal day, maturity and packaging effects, lot variability, grading into price classes, chilling penalty | Quantile gradient boosting (P10, P50, P90) with monotone constraints, trained to reproduce the kinetic model |
| Code | `core/salva_core/kinetics.py`, `loss_model/kinetic_model.py` | `ml/train.py`, `core/salva_core/loss_model/lgbm_model.py` |
| Parameters | `data/reference/products.yaml` (each with value, unit, source, note) | `ml/artifacts/models/lgbm-2.0.0-8795c6c2-s42/` |

The features come from one function (`salva_core.features.assemble`) used both to generate
training data and in production.

## Data

Synthetic dataset `synth-g2.0.0-s42-8795c6c2` produced by `ml/generate.py` (Latin hypercube over
age, remaining transit, delay, temperature shocks, transit factor, storage), labels by the
kinetic model including lot-to-lot variability. Split by lot (no lot appears in two splits); an
extrapolation set (temperature above 34 degC or age above 96 h) is kept apart and reported only.

## Evaluation (synthetic test set, thresholds pre-registered in `ml/params/go_nogo.yaml`)

| Criterion | Result | Threshold | Status |
|---|---|---|---|
| P50 fidelity to the kinetic model (MAE) | 0.0255 | below 0.03 | pass |
| P10-P90 coverage of realised synthetic losses | 0.761 (95 % CI over lots 0.732-0.791) | 0.76-0.84 | pass |
| Monotonicity violations | 1440 | 0 | **fail** |
| Agreement of recommended decision with the kinetic model | 0.945 | at least 0.85 | pass |
| Latency, 10,000 rows (median) | 106 ms | below 300 ms | pass |

**Verdict: LIGHTGBM NO-GO.** The kinetic model stays in production; the LightGBM package is
registered as experimental (`ml/artifacts/active.json`) and is never used for analyses.
Full report: `ml/reports/lgbm-2.0.0-8795c6c2-s42/report.md`. These numbers were produced locally
with LightGBM 4.6.0; rerun `python -m ml.evaluate` to reproduce them.

For reference, against realised synthetic losses the kinetic model itself reaches a P50 MAE of
0.075 and a coverage of 0.771: lot-to-lot variability is irreducible for any model.

## Known limitations

- Labels come from a kinetic model, not field data; parameters are literature ranges or
  assumptions (the assumptions page of the application lists each one with its source).
- Air temperature is not product temperature; the packaging offset is assumed.
- No humidity, ethylene, vibration or handling model; chilling injury is a configured penalty.
- Market absorption, prices and transport costs are reference assumptions the user can edit.
- Feedback (decisions and real results) only observes the action that was taken.

## Validation plan

Design document, section on field validation: 5-10 interviews with traders and transporters,
15-30 observed lots compared against the predicted interval, and an expert review of
recommendations. None of it has been carried out yet.
