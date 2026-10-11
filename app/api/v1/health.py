import importlib.util

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.services import engines

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health: database, engine/model version, explanation layer")
def health(db: Session = Depends(get_db)):
    model = engines.model_info()
    body = {"status": "ok", "database": "up", "model": model,
            "explanation_layer": importlib.util.find_spec("app.llm") is not None,
            "auth_enabled": get_settings().auth_enabled}
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({**body, "status": "down", "database": "down"}, status_code=503)
    if model is None:
        body["status"] = "degraded"
    return body
