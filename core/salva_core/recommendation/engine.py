"""Deterministic risk-aware choice over Monte Carlo scenario results."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ..simulation.models import ScenarioResult
from .policy import Policy, Recommendation
from .rationale import rationale_codes


def _score(result: ScenarioResult, policy: Policy) -> float:
    if result.net_p10 is None or result.net_p50 is None:
        raise ValueError(f"feasible result {result.id} is missing net P10/P50")
    if result.net_p10 > result.net_p50 + 1e-8:
        raise ValueError(f"result {result.id} violates net P10 <= P50")
    downside = max(0.0, result.net_p50 - result.net_p10)
    return float(result.net_p50 - policy.lam * downside)


def _probabilities(results: Sequence[ScenarioResult]) -> dict[str, float]:
    eligible = [r for r in results if r.feasible and not r.discouraged]
    if not eligible:
        return {}
    if len(eligible) == 1:
        return {eligible[0].id: 1.0}

    supplied = np.array([max(0.0, float(r.prob_best)) for r in eligible], dtype=float)
    if np.all(np.isfinite(supplied)) and float(supplied.sum()) > 0:
        supplied /= supplied.sum()
        return {r.id: float(p) for r, p in zip(eligible, supplied, strict=True)}

    vectors = [np.asarray(r.net_draws, dtype=float) for r in eligible]
    if (
        all(x.ndim == 1 and x.size > 0 for x in vectors)
        and len({x.size for x in vectors}) == 1
    ):
        stacked = np.vstack(vectors)
        best = np.max(stacked, axis=0)
        ties = np.isclose(stacked, best[None, :], rtol=1e-10, atol=1e-8)
        probabilities = np.mean(ties / np.sum(ties, axis=0, keepdims=True), axis=1)
        return {r.id: float(p) for r, p in zip(eligible, probabilities, strict=True)}
    # External adapters may provide summaries only. Keep the recommendation possible,
    # but do not manufacture confidence without Monte Carlo probabilities.
    return {r.id: 0.0 for r in eligible}


def recommend(
    results: Sequence[ScenarioResult], policy: Policy | None = None
) -> Recommendation:
    """Return a best option or explicitly decline to name a winner.

    This two-argument adapter surface is stable for backend/ML consumers:
    ``recommend(results, policy)`` and the result's ``best_id`` field.
    """
    chosen_policy = policy or Policy()
    rows = list(results)
    if len({r.id for r in rows}) != len(rows):
        raise ValueError("scenario result ids must be unique")
    eligible = [r for r in rows if r.feasible and not r.discouraged]
    if not eligible:
        return Recommendation(
            best_id=None,
            confidence="none",
            rationale_codes=rationale_codes(rows, None, chosen_policy),
            ranked_ids=(),
            scores_fcfa=(),
            prob_best=0.0,
            gap_fraction=None,
            no_clear_winner=True,
        )

    scored = [(r, _score(r, chosen_policy)) for r in eligible]
    scored.sort(key=lambda pair: (-pair[1], pair[0].id))
    ranked = [row for row, _ in scored]
    scores = [value for _, value in scored]
    probabilities = _probabilities(rows)
    best = ranked[0]
    best_score = scores[0]
    best_probability = probabilities.get(best.id, 0.0)
    if len(scores) == 1:
        gap = 1.0
    else:
        denominator = max(
            1.0,
            abs(best_score),
            abs(scores[1]),
            float(chosen_policy.reference_value_fcfa or 0.0),
        )
        gap = max(0.0, (best_score - scores[1]) / denominator)

    unclear = (
        len(scored) > 1
        and gap < chosen_policy.materiality
        and best_probability < chosen_policy.clear_probability
    )
    if unclear:
        return Recommendation(
            best_id=None,
            confidence="none",
            rationale_codes=("NO_CLEAR_WINNER",),
            ranked_ids=tuple(row.id for row in ranked[:2]),
            scores_fcfa=tuple((row.id, value) for row, value in scored),
            prob_best=best_probability,
            gap_fraction=gap,
            no_clear_winner=True,
        )

    if (
        best_probability >= chosen_policy.high_probability
        and gap >= chosen_policy.high_gap_fraction
    ):
        confidence = "high"
    elif best_probability >= chosen_policy.medium_probability:
        confidence = "medium"
    else:
        confidence = "low"

    return Recommendation(
        best_id=best.id,
        confidence=confidence,
        rationale_codes=rationale_codes(rows, best, chosen_policy),
        ranked_ids=tuple(row.id for row in ranked),
        scores_fcfa=tuple((row.id, value) for row, value in scored),
        prob_best=best_probability,
        gap_fraction=gap,
        no_clear_winner=False,
    )


rank = recommend
