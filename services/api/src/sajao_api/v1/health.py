from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from sajao_api import __version__

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    version: str
    environment: Literal["dev", "staging", "production"]


@router.get("/health", operation_id="getHealth")
async def get_health(request: Request) -> Health:
    """Liveness check. Does not touch the database or any model provider."""
    return Health(
        status="ok", version=__version__, environment=request.app.state.settings.environment
    )
