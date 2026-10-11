from fastapi import APIRouter

from . import analyses, auth, explanations, lots, outcomes, reference

router = APIRouter(prefix="/api/v1")
for module in (reference, lots, analyses, explanations, auth, outcomes):
    router.include_router(module.router)
