---
doc: prd
status: draft
---
<!-- Consolidated from the team's design document (functional requirements FR-01 to FR-22).
     Review with the Skill Pack's 3-prd skill; set `status: approved` when the team agrees. -->

# SALVA — Product Requirements

Decision support for traders and cooperatives moving tomatoes to market: loss-of-value risk,
compared decisions and a checked explanation. Source: `scope.md > The Unique Kernel`.

## The Core Journey
1. The user signs in (or creates an organization) on a phone or a computer.
2. They create a lot: product, quantity, harvest time, maturity, packaging, departure, destination
   market, planned arrival, current delay. Weather, route duration and reference price appear
   automatically with their source.
3. SALVA analyses the lot: likely loss range (P10-P90) and central value, risk level, main
   factors, remaining shelf life.
4. The user simulates the decisions: each feasible option shows its net value range, recoverable
   kilograms and probability of being best; unavailable options show why.
5. The user may change assumptions (prices, market absorption, costs, storage duration) and rerun.
6. SALVA recommends an option with a confidence level, or says there is no clear winner, or names
   the least bad option when every route exceeds the shelf life, and explains why.
7. The user records the decision taken, then the real result; the lot is closed and kept in
   the history.

## Screens and Layout
Sign-in and registration; lot list (lots at risk first); new lot form; lot page with four steps
(Risk, Decisions, Recommendation, Follow-up); history; assumptions and limits; administration
(storage sites, users). A side menu on desktop, a collapsible menu on phones.

## Look and Feel
Sober field-office green with a ripening scale (green, amber, red) reserved for risk; the
P10-P90 band with its central tick is the recurring visual; no external fonts; readable at 360 px.

## Features and Behavior
- Lot entry with validation and readable errors (FR-01, FR-02), automatic enrichment with manual
  fallback (FR-03).
- Risk analysis with factors (FR-04 to FR-06), replay at a chosen date (FR-16).
- Feasible options, Monte Carlo simulation, optimized split (FR-07 to FR-09), assumption editing
  (FR-17), sensitivity grid (FR-19).
- Recommendation with confidence and the "no clear winner" state (FR-10).
- Explanation that cannot invent a number, template fallback, French or English (FR-11 to FR-13).
- History, decision and result recording (FR-14, FR-15).
- Administration of storage sites and users (FR-20, partial: markets are reference data).
- Accounts per organization (FR-21); permanent "model-based estimate, not a guarantee" notice
  with a link to the assumptions (FR-22).

## States and Boundaries
- **First use**: empty lot list with "create my first lot" and "prefill the example lot".
- **Weather unavailable**: a notice says which default temperature will be assumed.
- **Low risk**: the interface says no action is needed beyond continuing.
- **No clear winner / least bad**: shown explicitly, never hidden.
- **Language model off or rejected**: the template explanation is shown, labelled as such.
- **Permissions**: users only see their organization's data; only administrators manage sites
  and users.

## Product Decisions
- Net value in FCFA is the decision metric, kilograms secondary.
- Maturity and packaging are required inputs (they change the risk a lot).
- The kinetic model stays in production until a learned model passes its pre-registered gate.

## What We're Building
Everything in the core journey above, deployed as one web application with a PostgreSQL
database, documented and tested.

## Deferred From the POC
- Questions about an analysis (FR-18): needs a second validated language-model flow.
- Market management by administrators: markets are shared reference data for now.
- Password reset and e-mail verification.

## Possible Later Enhancements
Other products by configuration, live truck position, multi-lot optimization, field calibration
from recorded outcomes.

## Non-Goals
- Food-safety judgement: SALVA estimates commercial value, not edibility.
- Sensor integration: the users have no sensors.

## Open Questions
- Field validation: interviews and observed lots (can wait for after the hackathon).
