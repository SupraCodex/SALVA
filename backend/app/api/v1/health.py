from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.errors import ApiError
from app.services import engine

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Liveness only: answers without touching the database")
def live():
    # Used by the hosting platform and uptime monitors so that a sleeping serverless database
    # (and its free compute quota) is not woken up every few seconds.
    return {"status": "ok"}


@router.get("/health", summary="Service, database, active loss model and explanation provider")
def health(db: Session = Depends(get_db)):
    settings = get_settings()
    body: dict = {
        "status": "ok",
        "database": "up",
        "llm_provider": settings.llm_provider,
        "weather_enabled": settings.weather_enabled,
    }
    try:
        model = engine.loss_model("tomato")
        body["model"] = engine.model_descriptor(model)
    except ApiError:
        body["model"] = None
        body["status"] = "degraded"
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any database failure means 'down'
        return JSONResponse({**body, "status": "down", "database": "down"}, status_code=503)
    return body
