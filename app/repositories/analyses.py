"""Analyses are written once (with scenarios and recommendation) and never updated."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Analysis, Explanation, Lot, Recommendation, ScenarioRow


def get(db: Session, org_id: int, analysis_id: int) -> Analysis | None:
    return db.scalar(select(Analysis).join(Lot).where(Analysis.id == analysis_id, Lot.organization_id == org_id))


def latest_for_lot(db: Session, lot_id: int) -> Analysis | None:
    return db.scalar(select(Analysis).where(Analysis.lot_id == lot_id)
                     .order_by(Analysis.created_at.desc(), Analysis.id.desc()).limit(1))


def save(db: Session, analysis: Analysis, scenarios: list[ScenarioRow], reco: dict) -> Analysis:
    """reco: {'scenario_key': str|None, 'tied_keys': [...], ...} — keys are resolved to row ids here."""
    db.add(analysis)
    db.flush()
    by_key = {}
    for sc in scenarios:
        sc.analysis_id = analysis.id
        db.add(sc)
        db.flush()
        by_key[sc.key] = sc.id
    db.add(Recommendation(
        analysis_id=analysis.id,
        scenario_id=by_key.get(reco["scenario_key"]) if reco["scenario_key"] else None,
        confidence=reco["confidence"], rationale=reco["rationale"],
        tied=[by_key[k] for k in reco["tied_keys"] if k in by_key],
        policy={**reco["policy"], "ranking": [{**r, "scenario_id": by_key.get(r["scenario_id"])}
                                               for r in reco["ranking"]]},
    ))
    db.commit()
    db.expire_all()
    return db.get(Analysis, analysis.id)


def cached_explanation(db: Session, analysis_id: int, lang: str) -> Explanation | None:
    return db.scalar(select(Explanation).where(Explanation.analysis_id == analysis_id, Explanation.lang == lang)
                     .order_by(Explanation.id.desc()).limit(1))


def save_explanation(db: Session, e: Explanation) -> Explanation:
    db.add(e)
    db.commit()
    db.refresh(e)
    return e
