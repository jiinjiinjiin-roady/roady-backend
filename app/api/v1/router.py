from fastapi import APIRouter

from app.api.v1.endpoints import bootstrap, health, profiles

router = APIRouter()

router.include_router(bootstrap.router)
router.include_router(health.router)
router.include_router(profiles.router)
