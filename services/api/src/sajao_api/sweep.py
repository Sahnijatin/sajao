"""Jobs that stopped without saying so: started again, or failed with a reason.

A job is a room's own stages or one design request's. The worker moves its rows; if
the start was lost (the spawn failed, the worker never ran) its rows stay queued, and
if the worker died past its retries a row stays running. Neither reaches the app on
its own, so a schedule looks every few minutes:

- a row running longer than its job's limit (the worker's timeout times its tries,
  plus a margin) is failed with `timed_out`;
- a job whose rows are all queued and untouched for a while is started again (safe:
  every stage is idempotent and a finished stage is not run again), and failed with
  `timed_out` once it has waited far too long;
- a design request waits while its room is still being read: the room job starts it.

Pure: the store reads the rows and applies the decisions.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

logger = logging.getLogger(__name__)

# The worker's timeout per try, its tries, and a margin, by job.
RUNNING_LIMIT = {
    "room": timedelta(seconds=900 * 2 + 120),
    "designs": timedelta(seconds=300 * 2 + 120),
}
# A job queued and untouched this long lost its start.
LOST_AFTER = timedelta(minutes=3)
# A job still queued this long after it was made is failed rather than started again.
GIVE_UP_AFTER = timedelta(minutes=30)


@dataclass(frozen=True)
class Row:
    room_id: str
    request_id: str | None
    stage: str
    status: str
    updated_at: datetime
    waiting_since: datetime
    """When the job could first run: the room's creation, or for a design request the
    later of its creation and the end of the room's reading."""
    room_read: bool
    """The room's own stages are done and its twin is stored."""


@dataclass(frozen=True)
class Decision:
    action: str  # "restart" or "fail"
    room_id: str
    request_id: str | None
    stage: str | None = None


def decide(rows: Iterable[Row], now: datetime) -> list[Decision]:
    jobs: dict[tuple[str, str | None], list[Row]] = {}
    for row in rows:
        if row.stage == "render" and row.status == "queued":
            continue  # a render row from before the render stage ran: nothing moves it
        jobs.setdefault((row.room_id, row.request_id), []).append(row)
    out: list[Decision] = []
    for (room_id, request_id), job in sorted(jobs.items(), key=lambda kv: str(kv[0])):
        kind = "room" if request_id is None else "designs"
        if any(r.status == "failed" for r in job) or all(r.status == "done" for r in job):
            continue
        running = [r for r in job if r.status == "running"]
        if running:
            stuck = [r for r in running if now - r.updated_at > RUNNING_LIMIT[kind]]
            out += [Decision("fail", room_id, request_id, r.stage) for r in stuck]
            continue
        if kind == "designs" and not job[0].room_read:
            continue  # the room job starts it when the room is read
        if now - max(max(r.updated_at for r in job), job[0].waiting_since) < LOST_AFTER:
            continue
        if now - job[0].waiting_since > GIVE_UP_AFTER:
            first = next(r for r in job if r.status == "queued")
            out.append(Decision("fail", room_id, request_id, first.stage))
            continue
        out.append(Decision("restart", room_id, request_id))
    return out


class SweptStore(Protocol):
    async def sweep_rows(self) -> list[Row]: ...

    async def set_stage(
        self,
        room_id: str,
        stage: str,
        status: str,
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None: ...


class Starter(Protocol):
    async def start_room(self, room_id: str) -> None: ...

    async def start_designs(self, room_id: str, request_id: str) -> None: ...


async def sweep(store: SweptStore, launcher: Starter, now: datetime) -> list[Decision]:
    """Look once and act: start lost jobs again, fail stuck ones with timed_out."""
    decisions = decide(await store.sweep_rows(), now)
    for d in decisions:
        try:
            if d.action == "fail" and d.stage is not None:
                await store.set_stage(d.room_id, d.stage, "failed", "timed_out", d.request_id)
            elif d.request_id is None:
                await launcher.start_room(d.room_id)
            else:
                await launcher.start_designs(d.room_id, d.request_id)
        except Exception:
            logger.exception("sweep could not act on %s", d)
    return decisions
