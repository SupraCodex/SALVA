---
doc: scope
status: draft
---
<!-- Consolidated from the team's design document (SALVA_Document_de_Conception, v1.0,
     5 October 2026). The team reviews it with the Skill Pack's 2-scope skill and sets
     `status: approved` once it reflects their own decisions. -->

# SALVA

Decision support that tells a tomato trader, before the truck arrives, how much value a lot is
likely to lose and what to do about it.

## The Unique Kernel
Turn a few quickly entered facts about a lot in transit into a loss-of-value range, then into
compared decisions (continue, store, reroute, sell locally, split) with their uncertainty, and
explain the recommendation in plain language that cannot invent a number.

## Who It's For
A cooperative manager or trader in West Cameroon who ships tomatoes to Douala or Yaounde by
truck, has no sensors, works from a phone, and today decides on intuition when a truck is late
or the market looks saturated.

## The Core Loop
Open SALVA when a lot leaves or is delayed, enter or update the lot, read the risk, compare the
options, take the recommended decision (or another one), and later record what really happened.
They come back for every lot and every delay.

## Inspiration & Identity
Serious, sober and honest: a field tool, not a dashboard of alerts. Ranges rather than single
figures, sources visible on every value, "no clear winner" said openly. French first, English
available.

## Why This Matters to the Learner
Post-harvest losses of perishable produce are large in Cameroon and often come from decisions
taken too late with too little information; the team wants a tool small actors can use without
equipment.

## What "Working" Looks Like
A user creates the demonstration lot (500 kg of tomatoes, 12 h late, Douala), sees the likely
loss range, simulates the options, sees the optimized split when storage capacity and market
absorption bind, reads a checked explanation, and records the decision.

## The POC Boundary
One product (tomato), one corridor (West region to Douala and Yaounde), the five decisions,
P10/P50/P90 ranges, recommendation with confidence, checked explanation with a template
fallback, decision and result recording, French and English, accounts per organization.

## Later
Other products (plantain, fresh fish) as configuration; field calibration of the parameters;
live truck position; questions about an analysis (FR-18); market management by administrators.

## Explicitly Cut
- Sensors and IoT: the target users do not have them.
- Microservices: one team, one month; every network boundary costs time.
- A learned model presented as field-accurate: no field dataset exists; claiming it would be
  dishonest.
