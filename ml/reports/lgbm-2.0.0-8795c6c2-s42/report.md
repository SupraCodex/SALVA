Model: LightGBM (lgbm-2.0.0-8795c6c2-s42, pinball_custom_monotone)
Dataset version: synth-g2.0.0-s42-8795c6c2  (hash 8795c6c2beee)
Seed: 42
DATA TYPE: SYNTHETIC (labels from the kinetic model). Real-world validation: NOT PERFORMED.

P50 MAE (fidelity to kinetic, test): 0.0255  [PASS]  required < 0.03
P10-P90 coverage (test): 0.761  [PASS]  required in [0.76, 0.84]
  95% CI over lots [0.732, 0.791]; kinetic reference (perfect model) = 0.771
Monotonicity violations: 1440  [FAIL]  required <= 0
Recommendation agreement: 0.945  [PASS]  required >= 0.85

Latency (10k rows, median): 106.4 ms  [PASS]  required < 300 ms

GO/NO-GO: LIGHTGBM NO-GO
Reason:
  - monotonicity_violations: 1440 (required <= 0)
Production model: KineticModel   Experimental model: LightGBM
Thresholds file sha256: b74f91af85346cef...  integrity: OK

How good is the kinetic baseline? (labels include irreducible lot variability)
  kinetic: P50 MAE vs realised 0.0751 | coverage 0.771 | mean pinball 0.02118
  LightGBM: P50 MAE vs realised 0.0800 | coverage 0.761 | mean pinball 0.02277

Extrapolation set (temperature > 34 or age > 96 h; reported, NOT part of the verdict)
  fidelity P50 MAE 0.0362 (max 0.259) | coverage 1.000 | kinetic coverage 0.839

Pairwise ordering proxy (informational): agreement 0.970 on 1682 pairs
Global SHAP importance of the P50 model (share): degree_hours_above_ref=0.41, maturity=0.30, exposure_h=0.19, packaging=0.03, temp_mean_c=0.02
