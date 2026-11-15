from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sajao_api.auth import Principal, current_user

router = APIRouter(tags=["account"])


class Me(BaseModel):
    user_id: str
    is_guest: bool


@router.get("/me", operation_id="getMe")
async def get_me(user: Annotated[Principal, Depends(current_user)]) -> Me:
    """The caller's own identity. Guests have one too."""
    return Me(user_id=user.user_id, is_guest=user.is_guest)
