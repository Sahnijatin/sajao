"""Version 1 of the public API. Each product module adds its router here."""

from fastapi import APIRouter

from sajao_api.v1 import health

router = APIRouter(prefix="/v1")
router.include_router(health.router)
