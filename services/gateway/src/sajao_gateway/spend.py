"""Spend caps per user per day and globally per day.

A call reserves its estimated cost before it runs and settles to the real
cost afterwards, so concurrent calls cannot overshoot a cap together.
"""

import datetime
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sajao_gateway.errors import SpendCapExceededError


@dataclass(frozen=True)
class SpendCaps:
    per_user_daily_micro_inr: int
    global_daily_micro_inr: int


@dataclass(frozen=True)
class Reservation:
    day: datetime.date
    user_id: str | None
    amount_micro_inr: int


class SpendLedger(Protocol):
    async def reserve(self, user_id: str | None, amount_micro_inr: int) -> Reservation:
        """Hold the amount, or raise SpendCapExceededError without holding anything."""
        ...

    async def settle(self, reservation: Reservation, actual_micro_inr: int) -> None:
        """Replace the held amount with what the call really cost (0 if it failed)."""
        ...


def utc_today() -> datetime.date:
    return datetime.datetime.now(datetime.UTC).date()


class InMemorySpendLedger:
    """Counts in one process: for tests and single-worker jobs.

    Running services need a ledger shared across instances, with the same
    reserve and settle contract.
    """

    def __init__(self, caps: SpendCaps, today: Callable[[], datetime.date] = utc_today) -> None:
        self.caps = caps
        self._today = today
        self._global: defaultdict[datetime.date, int] = defaultdict(int)
        self._users: defaultdict[tuple[datetime.date, str], int] = defaultdict(int)

    async def reserve(self, user_id: str | None, amount_micro_inr: int) -> Reservation:
        day = self._today()
        if user_id is not None:
            spent = self._users[(day, user_id)]
            if spent + amount_micro_inr > self.caps.per_user_daily_micro_inr:
                raise SpendCapExceededError("user")
        if self._global[day] + amount_micro_inr > self.caps.global_daily_micro_inr:
            raise SpendCapExceededError("global")
        self._apply(day, user_id, amount_micro_inr)
        return Reservation(day, user_id, amount_micro_inr)

    async def settle(self, reservation: Reservation, actual_micro_inr: int) -> None:
        difference = actual_micro_inr - reservation.amount_micro_inr
        self._apply(reservation.day, reservation.user_id, difference)

    def spent_today(self, user_id: str | None = None) -> int:
        day = self._today()
        return self._global[day] if user_id is None else self._users[(day, user_id)]

    def _apply(self, day: datetime.date, user_id: str | None, amount: int) -> None:
        self._global[day] += amount
        if user_id is not None:
            self._users[(day, user_id)] += amount
