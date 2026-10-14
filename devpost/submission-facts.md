# Submission fact sheet

The hackathon's Skill Pack (`6-ship`) requires the project name, short description and other
submission answers to be **written by the team**. This page is not submission copy: it lists
verified facts and links so the text you write is accurate. Do not paste it as is.

## Required items

| Item | Status |
|---|---|
| Public GitHub repository with an open-source license (MIT) | Repository exists; check it is public before submitting |
| `devpost/scope.md`, `prd.md`, `spec.md` | Present as drafts; review and approve them with the Skill Pack |
| Demo video, public on YouTube or Vimeo, under 3 minutes, English or translated | To record (plan: `docs/demo-script.md`) |
| Project name, description, form fields, exit survey | To write by the team |
| Free access for judges during judging | Provide a hosted URL or rely on the video plus `docker compose up` |
| Deadline | 26 October 2026, 5:00 pm US Eastern time (10:00 pm in Cameroon) |

## Verified facts you may use

- Inputs: 8 fields for a lot; weather, route and reference price are filled in automatically.
- Outputs: loss-of-value range P10/P50/P90, risk level, main factors, shelf-life estimate.
- Decisions compared: continue, store, reroute, sell locally, optimized split; 2,000 simulations
  per option; net value in FCFA with its range and probability of being best.
- The explanation is checked: any number not present in the computed facts, certainty wording,
  another recommended option or the wrong language makes the system fall back to a template.
- Production model: kinetic model. LightGBM surrogate evaluated on synthetic data: fidelity,
  coverage, decision agreement (0.945) and latency pass; monotonicity fails, so it is NO-GO and
  stays experimental (`docs/model-card.md`).
- Interface in French and English, works at 360 px width; organizations, roles, storage sites.
- Questions about an analysis: "what if" questions are simulated by the engine, never answered by
  free text generation.
- Tests: core, ML pipeline, backend on PostgreSQL, frontend unit tests, eight browser scenarios.

## Facts you must not claim

- Field accuracy, loss reductions or revenue gains: nothing has been measured in the field.
- National loss statistics unless you cite a source you have checked yourself.
- That the language model was tested live: only mocked responses were tested in this build.

## Built with

Python, FastAPI, SQLAlchemy, PostgreSQL, NumPy, SciPy, LightGBM, React, TypeScript, esbuild,
Playwright, Open-Meteo; optional Google Gemini or OpenAI-compatible API.
