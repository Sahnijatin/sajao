import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from sajao_api.accounts import AccountStore
from sajao_api.auth import Principal, current_user
from sajao_api.pipeline import PipelineLauncher

router = APIRouter(tags=["account"])
logger = logging.getLogger(__name__)


class Me(BaseModel):
    user_id: str
    is_guest: bool


class AccountDeletion(BaseModel):
    status: str
    """deleting until the files, rooms and sign-in account are gone, then deleted."""


def get_accounts(request: Request) -> AccountStore:
    store: AccountStore = request.app.state.accounts
    return store


def get_launcher(request: Request) -> PipelineLauncher:
    launcher: PipelineLauncher = request.app.state.pipeline
    return launcher


User = Annotated[Principal, Depends(current_user)]


@router.get("/me", operation_id="getMe")
async def get_me(user: User) -> Me:
    """The caller's own identity. Guests have one too."""
    return Me(user_id=user.user_id, is_guest=user.is_guest)


@router.delete("/me", operation_id="deleteMe", status_code=202)
async def delete_me(
    user: User,
    accounts: Annotated[AccountStore, Depends(get_accounts)],
    launcher: Annotated[PipelineLauncher, Depends(get_launcher)],
) -> AccountDeletion:
    """Erase the caller's account and everything stored for it. There is no undo.

    The request is recorded and the erasure starts at once; it finishes within
    minutes. Safe to repeat: a repeat starts the erasure again where it stopped.
    """
    await accounts.request_deletion(user.user_id)
    try:
        await launcher.start_account_deletion(user.user_id)
    except Exception:
        # The request is recorded; a repeat of this call starts the erasure.
        logger.exception("account deletion did not start")
    finished = await accounts.deletion_finished(user.user_id)
    return AccountDeletion(status="deleted" if finished else "deleting")
