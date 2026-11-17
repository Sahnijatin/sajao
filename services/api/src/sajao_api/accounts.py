"""Erasing an account: the request, and the job that carries it out.

The API records the request and asks the job to start; the job erases the
user's files, then their rows, then their sign-in account, and marks the
request finished. Every step is safe to repeat, so a job that died half way
is simply run again.
"""

import logging
from typing import Protocol

from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)


class AccountStore(Protocol):
    async def request_deletion(self, user_id: str) -> bool:
        """Record that the user asked to be erased; False if already asked."""
        ...

    async def erase_rows(self, user_id: str) -> None:
        """Delete every row that belongs to the user."""
        ...

    async def finish_deletion(self, user_id: str) -> None: ...

    async def deletion_finished(self, user_id: str) -> bool | None:
        """None if never asked, else whether the erasure is complete."""
        ...

    async def unfinished_deletions(self) -> list[str]:
        """Users whose erasure was asked for and is not complete, oldest first."""
        ...


class UserFiles(Protocol):
    def erase(self, user_id: str) -> int:
        """Delete every stored file of the user; returns how many were deleted."""
        ...


class SignIn(Protocol):
    async def erase(self, user_id: str) -> None:
        """Delete the user's sign-in account. A user who is already gone is fine."""
        ...


async def erase_account(
    user_id: str, accounts: AccountStore, files: UserFiles, sign_in: SignIn
) -> int:
    """Erase everything of one user. Returns the number of files deleted."""
    # Files first: while the rows still exist a repeat can find nothing it missed,
    # because files are found by the user's folder, not through the rows.
    deleted = files.erase(user_id)
    await accounts.erase_rows(user_id)
    # Last, so a failure above leaves an account the person can still ask from.
    await sign_in.erase(user_id)
    await accounts.finish_deletion(user_id)
    logger.info("account erased: %d files", deleted)
    return deleted


class InMemoryAccountStore:
    """For local development and tests only: state lives in one process."""

    def __init__(self) -> None:
        self._requests: dict[str, bool] = {}
        self.erased: list[str] = []

    async def request_deletion(self, user_id: str) -> bool:
        if user_id in self._requests:
            return False
        self._requests[user_id] = False
        return True

    async def erase_rows(self, user_id: str) -> None:
        self.erased.append(user_id)

    async def finish_deletion(self, user_id: str) -> None:
        self._requests[user_id] = True

    async def deletion_finished(self, user_id: str) -> bool | None:
        return self._requests.get(user_id)

    async def unfinished_deletions(self) -> list[str]:
        return [user for user, finished in self._requests.items() if not finished]


_REQUEST = """
insert into private.account_deletions (user_id) values (%(user_id)s)
on conflict (user_id) do nothing
returning user_id
"""
# Rooms first: their stages and design requests go with them, and a capture
# cannot be deleted while a room points at it.
_ERASE = (
    "delete from public.rooms where user_id = %(user_id)s",
    "delete from public.captures where user_id = %(user_id)s",
    "delete from private.idempotency_keys where scope = %(user_id)s",
)
_FINISH = """
update private.account_deletions set finished_at = now()
where user_id = %(user_id)s and finished_at is null
"""
_READ = "select finished_at is not null from private.account_deletions where user_id = %(user_id)s"
_UNFINISHED = """
select user_id::text from private.account_deletions
where finished_at is null
order by requested_at
limit 100
"""


class PostgresAccountStore:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def request_deletion(self, user_id: str) -> bool:
        async with self._pool.connection() as connection:
            row = await (await connection.execute(_REQUEST, {"user_id": user_id})).fetchone()
        return row is not None

    async def erase_rows(self, user_id: str) -> None:
        async with self._pool.connection() as connection, connection.transaction():
            for statement in _ERASE:
                await connection.execute(statement, {"user_id": user_id})

    async def finish_deletion(self, user_id: str) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(_FINISH, {"user_id": user_id})

    async def deletion_finished(self, user_id: str) -> bool | None:
        async with self._pool.connection() as connection:
            row = await (await connection.execute(_READ, {"user_id": user_id})).fetchone()
        return row[0] if row is not None else None

    async def unfinished_deletions(self) -> list[str]:
        async with self._pool.connection() as connection:
            rows = await (await connection.execute(_UNFINISHED)).fetchall()
        return [row[0] for row in rows]
