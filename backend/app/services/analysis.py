"""Risk analysis of a lot (FR-04 to FR-06): derived features, loss P10/P50/P90, risk, factors.

Orchestration only: every number comes from ``salva_core``. The analysis is stored with its
exact inputs, their sources and the model version (NFR-06) and is never modified afterwards.
"""

from __future__ import annotations

import uuid

import numpy as np
from salva_core.contracts import LossDistribution
from salva_core.contracts import Lot as CoreLot
from salva_core.features import assemble
from salva_core.loss_model.factors import contributions
from salva_core.risk import classify_risk
from sqlalchemy.orm import Session

from app.db.models import Analysis, Lot
from app.deps import Caller
from app.errors import ApiError, field_error, not_found
from app.repositories import lots as lots_repo
from app.schemas.analysis import AnalysisCreate, AnalysisOut
from app.schemas.common import build
from app.services import engine, enrichment
from app.services.lots import get_or_404 as get_lot_or_404
from app.services.lots import hours_between, utcnow

FACTOR_EPS = 1e-3


def core_lot(lot: Lot, analysis: Analysis) -> CoreLot:
    """Rebuild the core view of a lot exactly as it was analysed (used by simulations too)."""
    f = analysis.features
    return CoreLot(
        kg=float(lot.quantity_kg),
        maturity=lot.maturity,
        packaging=lot.packaging,
        age_h=float(f["age_h"]),
        remaining_h=float(f["remaining_transit_h"]),
        temp_c=float(f["temp_air_c"]),
        product=lot.product_code,
        delay_h=float(f["delay_h"]),
        diurnal_amp_c=float(f["diurnal_amp_c"]),
    )


def analyze(db: Session, caller: Caller, lot_id: uuid.UUID, body: AnalysisCreate) -> Analysis:
    lot = get_lot_or_404(db, caller, lot_id)
    if lot.status == "closed":
        raise ApiError(409, "lot-closed", "This lot is closed.")
    now = body.analysis_at or utcnow()
    if now < lot.harvested_at:
        raise field_error("analysis_at", "before_harvest", "analysis time must be after harvest")
    if hours_between(now, lot.harvested_at) > 30 * 24:
        raise field_error(
            "analysis_at",
            "too_late",
            "analysis time is more than 30 days after harvest",
        )
    p = engine.params(lot.product_code)
    model = engine.loss_model(lot.product_code)

    temp = enrichment.temperature(lot, now)
    price = enrichment.price(lot)
    age_h = max(0.0, hours_between(now, lot.harvested_at))
    remaining_h = max(0.0, hours_between(lot.eta_current_at, now))
    total_delay = max(0.0, hours_between(lot.eta_current_at, lot.eta_planned_at))
    delay_h = min(total_delay, remaining_h)  # only the part of the delay still ahead matters

    f = assemble(
        p,
        maturity=lot.maturity,
        packaging=lot.packaging,
        age_h=age_h,
        remaining_h=remaining_h,
        temp_air_c=temp.mean.value,
        delay_h=delay_h,
        diurnal_amp_c=temp.half_amplitude.value,
        product=lot.product_code,
    )
    dist = model.predict(f)
    p10, p50, p90 = (float(np.clip(x, 0.0, 1.0)) for x in (dist.p10, dist.p50, dist.p90))
    p10, p50, p90 = sorted((p10, p50, p90))
    risk = classify_risk(LossDistribution(p10, p50, p90), p)

    factors = []
    for name, value in contributions(model, f, p).items():
        c = float(np.ravel(value)[0])
        direction = "increases_risk" if c > FACTOR_EPS else "decreases_risk" if c < -FACTOR_EPS else "neutral"
        factors.append({"name": name, "contribution": round(c, 4), "direction": direction})
    factors.sort(key=lambda item: abs(item["contribution"]), reverse=True)

    shelf_life = None
    estimate = getattr(model, "remaining_shelf_life_p50_h", None)
    if estimate is not None:
        value = estimate(f)
        if value is not None:
            shelf_life = round(float(np.asarray(value).flat[0]), 1)

    extrapolated = list(getattr(dist, "extrapolated_features", ()) or ())
    descriptor = engine.model_descriptor(model)
    features = {
        "product": lot.product_code,
        "quantity_kg": float(lot.quantity_kg),
        "maturity": lot.maturity,
        "packaging": lot.packaging,
        "age_h": round(age_h, 3),
        "remaining_transit_h": round(remaining_h, 3),
        "delay_h": round(delay_h, 3),
        "total_delay_h": round(total_delay, 3),
        "temp_air_c": temp.mean.value,
        "diurnal_amp_c": temp.half_amplitude.value,
        "product_temp_mean_c": round(float(np.asarray(f.temp_mean_c).flat[0]), 2),
        "product_temp_max_c": round(float(np.asarray(f.temp_max_c).flat[0]), 2),
        "degree_hours_above_ref": round(float(np.asarray(f.degree_hours_above_ref).flat[0]), 1),
        "exposure_h": round(float(np.asarray(f.exposure_h).flat[0]), 2),
        "price_fcfa_kg": price.value,
    }
    sources = {
        "temp_air_c": temp.mean.source,
        "diurnal_amp_c": temp.half_amplitude.source,
        "price_fcfa_kg": price.source,
        "harvested_at": "user",
        "eta": "user",
        "product_parameters": f"products.yaml sha256:{p.file_sha256[:12]}",
    }
    analysis = Analysis(
        lot_id=lot.id,
        model_name=descriptor["name"],
        model_version=descriptor["version"],
        model_fallback=descriptor["fallback"],
        analysis_at=now,
        replay=body.analysis_at is not None,
        features=features,
        feature_sources=sources,
        loss_p10=p10,
        loss_p50=p50,
        loss_p90=p90,
        risk_level=risk.level,
        risk_detail=risk.as_dict(),
        top_factors=factors,
        shelf_life_p50_h=shelf_life,
        extrapolated=extrapolated,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def get_or_404(db: Session, caller: Caller, analysis_id: uuid.UUID) -> Analysis:
    analysis = lots_repo.analysis(db, caller.organization_id, analysis_id)
    if analysis is None:
        raise not_found("Analysis")
    return analysis


def to_out(a: Analysis) -> AnalysisOut:
    f, src = a.features, a.feature_sources
    return build(
        AnalysisOut,
        id=a.id,
        lot_id=a.lot_id,
        analysis_at=a.analysis_at,
        replay=a.replay,
        model={
            "name": a.model_name,
            "version": a.model_version,
            "fallback": a.model_fallback,
        },
        inputs={
            "age_h": f["age_h"],
            "remaining_transit_h": f["remaining_transit_h"],
            "delay_h": f["delay_h"],
            "total_delay_h": f.get("total_delay_h", f["delay_h"]),
            "temp_mean_c": {"value": f["temp_air_c"], "source": src["temp_air_c"]},
            "diurnal_amp_c": {
                "value": f["diurnal_amp_c"],
                "source": src["diurnal_amp_c"],
            },
            "product_temp_mean_c": f["product_temp_mean_c"],
            "degree_hours_above_ref": f["degree_hours_above_ref"],
            "price_fcfa_kg": {
                "value": f["price_fcfa_kg"],
                "source": src["price_fcfa_kg"],
            },
            "quantity_kg": f["quantity_kg"],
            "maturity": f["maturity"],
            "packaging": f["packaging"],
        },
        risk={
            "level": a.risk_level,
            "loss_fraction": {"p10": a.loss_p10, "p50": a.loss_p50, "p90": a.loss_p90},
            "interval_width": a.risk_detail.get("interval_width", a.loss_p90 - a.loss_p10),
            "loss_reason": a.risk_detail.get("loss_reason", ""),
            "uncertainty_reason": a.risk_detail.get("uncertainty_reason", ""),
        },
        top_factors=a.top_factors,
        shelf_life_p50_h=a.shelf_life_p50_h,
        extrapolated_features=a.extrapolated,
        created_at=a.created_at,
    )
