# Demo video plan (under 3 minutes)

The hackathon requires a public YouTube or Vimeo video **shorter than 3 minutes**, in English
(or with an English translation), showing the project working. The narration is yours to write;
this page only fixes the sequence, the data and the checks so that the recording is reproducible.

## Before recording

1. Start the application (`docker compose up` with `SEED_DEMO=true`, or `make demo && make run`).
   For a hosted instance run `./scripts/warmup.sh <url>` a few minutes before.
2. Sign in with the demo account (password from `DEMO_USER_PASSWORD` or the seed output). Never
   show the password, the `.env` file or a terminal with secrets.
3. Switch the interface to **EN** (bottom of the side menu).
4. Browser window about 1280 x 800, zoom 100 %, notifications off.

## Sequence

| Time | Screen | What to show |
|---|---|---|
| 0:00-0:20 | Sign-in page | The problem in one sentence; what SALVA does (risk, decisions, explanation). |
| 0:20-0:45 | New lot, "Prefill the example lot" | Eight inputs; the automatic weather and route check under the form. Do not submit; go back to the seeded demo lot instead (its dates are fixed). |
| 0:45-1:15 | Demo lot, Risk tab | Tick "Analyse at another date", set **3 Oct 2026 09:00** in Cameroon time (08:00 UTC), run. Show the P10-P90 band, the risk level, the main factors and the source badges (assumption, reference value). |
| 1:15-1:55 | Decisions tab | "Simulate the decisions": scenario cards with net value ranges and "best option in x % of simulations", the comparison chart, the unavailable storage option and its reason. |
| 1:55-2:20 | Decisions tab, "Change the assumptions" | Set **Absorption at Marche Mboppi (full-price kg) = 150** and run again: the optimized split appears (in our local run about 254 kg to Douala and 246 kg to Yaounde) and the assumption carries a "changed" badge. Optionally "Compute the switching points". |
| 2:20-2:50 | Recommendation tab | The recommendation, its confidence, the gain over continuing as planned, the "least bad" warning (every route exceeds the estimated shelf life on this lot), the explanation and its source badge; click the example question "What if the delay were 24 hours?" to show a simulated answer; then "I took this decision". |
| 2:50-2:59 | Assumptions page | Model, parameters with sources, known limits: "model-based estimate, not validated on field data". |

Figures on screen are those computed by the system at recording time; do not quote figures from
this page or from the design document in the narration.

## Checks after recording

- Duration under 3:00; the working product is visible (not only slides).
- No credential, e-mail inbox, token or personal file visible.
- The video is public (or unlisted with link access) and the link opens without signing in.
