"""The sweeper starts lost jobs again and fails stuck ones with a reason the app shows."""

from datetime import UTC, datetime, timedelta

from sajao_api.pipeline import RecordingLauncher
from sajao_api.sweep import Decision, Row, decide, sweep

NOW = datetime(2026, 11, 19, 18, 30, tzinfo=UTC)


def ago(minutes: float) -> datetime:
    return NOW - timedelta(minutes=minutes)


def room_rows(
    *statuses: str, updated: float = 10, made: float = 10, read: bool = False
) -> list[Row]:
    names = ("measure", "inventory")
    return [
        Row("r1", None, name, status, ago(updated), ago(made), read)
        for name, status in zip(names, statuses, strict=True)
    ]


def design_rows(
    *statuses: str, updated: float = 10, since: float = 10, read: bool = True
) -> list[Row]:
    names = ("spec", "placement", "render")
    return [
        Row("r1", "q1", name, status, ago(updated), ago(since), read)
        for name, status in zip(names, statuses, strict=False)
    ]


def test_a_room_whose_start_was_lost_is_started_again() -> None:
    assert decide(room_rows("queued", "queued"), NOW) == [Decision("restart", "r1", None)]


def test_a_room_just_made_is_left_to_start() -> None:
    assert decide(room_rows("queued", "queued", updated=1, made=1), NOW) == []


def test_a_room_that_never_started_in_half_an_hour_fails_timed_out() -> None:
    rows = room_rows("queued", "queued", updated=40, made=40)
    assert decide(rows, NOW) == [Decision("fail", "r1", None, "measure")]


def test_a_stage_running_past_the_workers_limit_fails_timed_out() -> None:
    assert decide(room_rows("running", "queued", updated=40), NOW) == [
        Decision("fail", "r1", None, "measure")
    ]
    assert decide(room_rows("running", "queued", updated=20), NOW) == []


def test_a_room_that_died_between_stages_is_started_again() -> None:
    assert decide(room_rows("done", "queued", updated=5), NOW) == [Decision("restart", "r1", None)]


def test_finished_and_failed_jobs_are_left_alone() -> None:
    assert decide(room_rows("done", "done"), NOW) == []
    assert decide(room_rows("failed", "queued"), NOW) == []


def test_designs_wait_for_the_room_and_then_are_started_again_if_lost() -> None:
    assert decide(design_rows("queued", "queued", read=False), NOW) == []
    assert decide(design_rows("queued", "queued"), NOW) == [Decision("restart", "r1", "q1")]


def test_a_render_row_nothing_moves_does_not_hold_a_request_open() -> None:
    assert decide(design_rows("done", "done", "queued"), NOW) == []


async def test_the_sweep_acts_on_its_decisions() -> None:
    class Store:
        def __init__(self) -> None:
            self.moved: list[tuple[str, str, str, str | None, str | None]] = []

        async def sweep_rows(self) -> list[Row]:
            return room_rows("running", "queued", updated=40) + design_rows("queued", "queued")

        async def set_stage(
            self,
            room_id: str,
            stage: str,
            status: str,
            detail: str | None = None,
            request_id: str | None = None,
        ) -> None:
            self.moved.append((room_id, stage, status, detail, request_id))

    store, launcher = Store(), RecordingLauncher()
    await sweep(store, launcher, NOW)
    assert store.moved == [("r1", "measure", "failed", "timed_out", None)]
    assert launcher.designs == [("r1", "q1")]
