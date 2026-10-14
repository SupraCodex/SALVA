# Architecture decisions

Short records of the choices that shape the code. Each states the context, the decision and the
consequence accepted.

## ADR-1 Numbers come only from computation engines

Context: a language model can produce plausible but wrong figures. Decision: risk, scenarios and
recommendation are computed by `core/`; the explanation layer receives JSON facts and its text is
rejected if it contains a number absent from them, certainty wording, another recommended option,
the wrong language or markup. A template explanation is always computed. Consequence: the product
works with the language model switched off (`LLM_PROVIDER=template`, the default).

## ADR-2 Kinetic model in production until a learned model passes its gate

Context: no public field dataset exists for this corridor. Decision: a kinetic model with
documented parameters is the reference; a LightGBM surrogate is trained on synthetic data and
promoted only on a `LIGHTGBM GO` verdict against thresholds fixed before evaluation. Consequence:
the current production model is kinetic (the surrogate fails the monotonicity criterion), and
every screen states that estimates are not validated on field data.

## ADR-3 Modular monolith

Context: a small team and a short delivery window. Decision: one FastAPI application that also
serves the built interface, a pure Python `core/` library without I/O, and an offline `ml/`
pipeline. Consequence: one deployment, one origin (strict CSP, simple cookie scope); scaling out
would require a shared rate-limit store.

## ADR-4 Decisions are compared on net value with their uncertainty

Context: kilograms alone ignore prices and transport costs. Decision: every option is simulated
with the same random draws and compared on net value in FCFA (P10/P50/P90), with recoverable
kilograms as a secondary indicator; capacity and market absorption are hard constraints and the
split is solved as a linear programme. When no option dominates, the interface says so; when all
options exceed the estimated shelf life, it names the least bad one and warns.

## ADR-5 Small, dependency-light interface

Context: users on phones and slow connections. Decision: React with a hand-written router,
dictionary-based French/English, no UI kit, no external fonts or CDN, bundled by esbuild.
Consequence: one JavaScript bundle of about 300 KB before compression; the npm lockfile must be
generated on a machine with registry access (`npm install`), which was not possible in the
environment where this version was assembled.
