import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import errors
from app import logging as app_logging
from app.api.v1 import router as v1
from app.api.v1.health import router as health_router
from app.config import get_settings

app_logging.setup()
log = logging.getLogger("salva")

app = FastAPI(
    title="SALVA API",
    version="0.1.0",
    description="Spoilage-Aware Logistics & Value Allocation: decision support for perishable produce.\n\n"
                "Every figure is a **model estimate, not validated in the field** "
                "(`disclaimer_code: MODEL_ESTIMATE_NOT_FIELD_VALIDATED`).",
)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().allowed_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])
errors.install(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:10]}"
    request.state.request_id = rid
    t0 = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    log.info("request", extra={"request_id": rid, "path": f"{request.method} {request.url.path}",
                               "status": response.status_code, "ms": round((time.perf_counter() - t0) * 1000, 1)})
    return response


app.include_router(health_router)
app.include_router(v1)
