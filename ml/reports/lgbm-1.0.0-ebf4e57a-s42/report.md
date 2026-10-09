Model: LightGBM (lgbm-1.0.0-ebf4e57a-s42, pinball_custom_monotone)
Dataset version: synth-g1.0.0-s42-ebf4e57a  (hash ebf4e57a9281)
Seed: 42
DATA TYPE: SYNTHETIC (labels from the kinetic model). Real-world validation: NOT PERFORMED.

P50 MAE (fidelity to kinetic, test): 0.0235  [PASS]  required < 0.03
P10-P90 coverage (test): 0.769  [PASS]  required in [0.76, 0.84]
  95% CI over lots [0.739, 0.797]; kinetic reference (perfect model) = 0.769
Monotonicity violations: 0  [PASS]  required <= 0
Recommendation agreement: n/a  [FAIL]  required >= 0.85
  NOT EVALUATED: P1 engines not available yet (No module named 'salva_core.recommendation')
Latency (10k rows, median): 199.0 ms  [PASS]  required < 300 ms

GO/NO-GO: LIGHTGBM NO-GO
Reason:
  - decision_agreement: None (required >= 0.85) NOT EVALUATED: P1 engines not available yet (No module named 'salva_core.recommendation')
Production model: KineticModel   Experimental model: LightGBM
Thresholds file sha256: b74f91af85346cef...  integrity: OK

How good is the kinetic baseline? (labels include irreducible lot variability)
  kinetic: P50 MAE vs realised 0.0712 | coverage 0.769 | mean pinball 0.02023
  LightGBM: P50 MAE vs realised 0.0771 | coverage 0.769 | mean pinball 0.02205

Extrapolation set (temperature > 34 or age > 96 h; reported, NOT part of the verdict)
  fidelity P50 MAE 0.0383 (max 0.253) | coverage 0.780 | kinetic coverage 0.822

Pairwise ordering proxy (informational): agreement 0.977 on 1723 pairs
Global SHAP importance of the P50 model (share): degree_hours_above_ref=0.43, maturity=0.29, exposure_h=0.17, packaging=0.03, temp_mean_c=0.03
