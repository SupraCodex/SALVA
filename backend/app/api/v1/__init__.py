from fastapi import APIRouter

from . import admin, analyses, auth, health, lots, reference

router = APIRouter(prefix="/api/v1")
for module in (health, auth, reference, admin, lots, analyses):
    router.include_router(module.router)
