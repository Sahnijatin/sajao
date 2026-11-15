"""Gateway behavior, tested with fake providers only: no network and no keys."""

import asyncio
import datetime
import json
import logging
from typing import Any

import pytest

from sajao_gateway import (
    AllProvidersFailedError,
    InMemoryCallLog,
    InMemoryResponseCache,
    InMemorySpendLedger,
    InvalidOutputError,
    JsonCallLog,
    ModelGateway,
    ModelRequest,
    ProviderError,
    ProviderResult,
    RetryPolicy,
    SpendCapExceededError,
    SpendCaps,
)
from sajao_gateway.testing import FakeProvider

GOOD = ProviderResult({"palette": "warm"}, cost_micro_inr=400)
OTHER = ProviderResult({"palette": "cool"}, cost_micro_inr=150)
DOWN = ProviderError("503 from provider")
REFUSED = ProviderError("request rejected", retryable=False)
ROOMY = SpendCaps(per_user_daily_micro_inr=10**9, global_daily_micro_inr=10**9)


def request(**changes: Any) -> ModelRequest:
    fields: dict[str, Any] = {
        "task": "brief_to_spec",
        "modality": "text",
        "prompt_id": "brief_to_spec@1",
        "payload": {"budget": 150000, "style": "japandi"},
        "user_id": "user-1",
    }
    return ModelRequest(**{**fields, **changes})


def accept(_result: ProviderResult) -> None:
    return None


def needs_palette(result: ProviderResult) -> None:
    if "palette" not in result.output:
        raise InvalidOutputError("missing palette")


class Harness:
    """A gateway with a controllable clock and a record of every backoff sleep."""

    def __init__(self, *providers: FakeProvider, caps: SpendCaps = ROOMY, **options: Any) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []
        self.log = InMemoryCallLog()
        self.cache = InMemoryResponseCache()
        self.ledger = InMemorySpendLedger(caps, today=lambda: datetime.date(2000, 1, 1))
        self.gateway = ModelGateway(
            providers,
            ledger=self.ledger,
            cache=self.cache,
            call_log=self.log,
            clock=lambda: self.now,
            sleep=self._sleep,
            jitter=lambda: 1.0,
            **options,
        )

    async def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def outcomes(self) -> list[tuple[str | None, str]]:
        return [(entry.provider, entry.outcome) for entry in self.log.entries]


# --- fallback chain -----------------------------------------------------------


async def test_the_primary_answers_when_it_is_healthy() -> None:
    primary, fallback = FakeProvider("primary", [GOOD]), FakeProvider("fallback", [OTHER])
    h = Harness(primary, fallback)

    response = await h.gateway.call(request(), validate=accept)

    assert (response.provider, response.output) == ("primary", {"palette": "warm"})
    assert not response.cached and not response.degraded
    assert fallback.calls == []


async def test_a_failing_primary_falls_back_after_its_retries() -> None:
    primary, fallback = FakeProvider("primary", [DOWN]), FakeProvider("fallback", [OTHER])
    h = Harness(primary, fallback)

    response = await h.gateway.call(request(), validate=accept)

    assert response.provider == "fallback"
    assert len(primary.calls) == 3
    assert h.outcomes() == [("primary", "error")] * 3 + [("fallback", "success")]


async def test_retries_back_off_exponentially_up_to_a_ceiling() -> None:
    primary = FakeProvider("primary", [DOWN, DOWN, DOWN, DOWN, GOOD])
    h = Harness(
        primary, retry=RetryPolicy(max_attempts=5, base_delay_seconds=1, max_delay_seconds=4)
    )

    await h.gateway.call(request(), validate=accept)

    assert h.sleeps == [1, 2, 4, 4]


async def test_an_error_that_cannot_succeed_is_not_retried() -> None:
    primary, fallback = FakeProvider("primary", [REFUSED]), FakeProvider("fallback", [OTHER])
    h = Harness(primary, fallback)

    response = await h.gateway.call(request(), validate=accept)

    assert len(primary.calls) == 1
    assert h.sleeps == []
    assert response.provider == "fallback"


async def test_an_unexpected_exception_from_one_provider_does_not_stop_the_chain() -> None:
    primary, fallback = FakeProvider("primary", [KeyError("sdk bug")]), FakeProvider("f", [OTHER])
    h = Harness(primary, fallback, retry=RetryPolicy(max_attempts=1))

    assert (await h.gateway.call(request(), validate=accept)).provider == "f"
    assert h.log.entries[0].error == "KeyError"


async def test_a_slow_provider_times_out_and_falls_back() -> None:
    stuck = FakeProvider("primary", [GOOD], hold=asyncio.Event())
    fallback = FakeProvider("fallback", [OTHER])
    gateway = ModelGateway(
        [stuck, fallback],
        ledger=InMemorySpendLedger(ROOMY),
        call_log=(log := InMemoryCallLog()),
        retry=RetryPolicy(max_attempts=1, timeout_seconds=0.05),
    )

    response = await gateway.call(request(), validate=accept)

    assert response.provider == "fallback"
    assert log.entries[0].error == "timeout"


async def test_providers_that_cannot_do_the_modality_are_skipped() -> None:
    text_only = FakeProvider("text-only", [GOOD], modalities=frozenset({"text"}))
    image = FakeProvider("image", [OTHER], modalities=frozenset({"image"}))
    h = Harness(text_only, image)

    response = await h.gateway.call(request(modality="image"), validate=accept)

    assert response.provider == "image"
    assert text_only.calls == []


async def test_when_everything_fails_the_caller_gets_a_clear_error() -> None:
    h = Harness(FakeProvider("primary", [DOWN]), FakeProvider("fallback", [DOWN]))
    with pytest.raises(AllProvidersFailedError):
        await h.gateway.call(request(), validate=accept)


async def test_the_chain_ends_in_the_degraded_mode_so_the_app_never_stops() -> None:
    h = Harness(FakeProvider("primary", [DOWN]), FakeProvider("fallback", [DOWN]))

    async def rules(_request: ModelRequest) -> ProviderResult:
        return ProviderResult({"palette": "neutral", "source": "rules"})

    response = await h.gateway.call(request(), validate=needs_palette, degraded=rules)

    assert response.degraded
    assert response.output["source"] == "rules"
    assert response.cost_micro_inr == 0
    assert h.outcomes()[-1] == ("degraded", "degraded")
    # A degraded answer is never cached: the next call tries the models again.
    assert await h.cache.get(h.log.entries[-1].cache_key) is None


# --- output validation --------------------------------------------------------


async def test_an_invalid_output_counts_as_a_failure_and_is_never_returned() -> None:
    primary = FakeProvider("primary", [ProviderResult({"oops": True}, cost_micro_inr=400)])
    fallback = FakeProvider("fallback", [OTHER])
    h = Harness(primary, fallback, retry=RetryPolicy(max_attempts=2))

    response = await h.gateway.call(request(), validate=needs_palette)

    assert response.output == {"palette": "cool"}
    assert h.outcomes() == [("primary", "invalid_output")] * 2 + [("fallback", "success")]


async def test_an_invalid_output_is_not_cached() -> None:
    primary = FakeProvider("primary", [ProviderResult({"oops": True}), GOOD])
    h = Harness(primary)

    response = await h.gateway.call(request(), validate=needs_palette)

    assert response.output == {"palette": "warm"}
    assert (await h.gateway.call(request(), validate=needs_palette)).cached


# --- circuit breaker ----------------------------------------------------------


async def test_the_circuit_opens_after_repeated_failures_then_probes_and_closes() -> None:
    primary, fallback = FakeProvider("primary", [DOWN]), FakeProvider("fallback", [OTHER])
    h = Harness(
        primary,
        fallback,
        retry=RetryPolicy(max_attempts=1),
        breaker_failure_threshold=2,
        breaker_cooldown_seconds=30,
    )

    async def call(n: int) -> str:
        return (await h.gateway.call(request(payload={"n": n}), validate=accept)).provider

    assert [await call(1), await call(2)] == ["fallback", "fallback"]
    assert len(primary.calls) == 2

    # Open: the primary is skipped without being called.
    assert await call(3) == "fallback"
    assert len(primary.calls) == 2
    assert ("primary", "circuit_open") in h.outcomes()

    # After the cooldown one trial goes through. It fails, so the circuit reopens.
    h.now += 31
    assert await call(4) == "fallback"
    assert len(primary.calls) == 3
    assert await call(5) == "fallback"
    assert len(primary.calls) == 3

    # The provider recovers: the next trial succeeds and the circuit closes.
    primary.script = [GOOD]
    h.now += 31
    assert await call(6) == "primary"
    assert await call(7) == "primary"


async def test_a_success_resets_the_failure_count() -> None:
    primary = FakeProvider("primary", [DOWN, GOOD, DOWN, GOOD])
    fallback = FakeProvider("fallback", [OTHER])
    h = Harness(primary, fallback, retry=RetryPolicy(max_attempts=1), breaker_failure_threshold=2)

    providers = [
        (await h.gateway.call(request(payload={"n": n}), validate=accept)).provider
        for n in range(4)
    ]

    assert providers == ["fallback", "primary", "fallback", "primary"]
    assert ("primary", "circuit_open") not in h.outcomes()


# --- spend caps ---------------------------------------------------------------


async def test_spend_is_counted_per_user_and_globally_at_the_real_cost() -> None:
    h = Harness(FakeProvider("primary", [GOOD], estimated_cost_micro_inr=1_000))

    await h.gateway.call(request(user_id="a", payload={"n": 1}), validate=accept)
    await h.gateway.call(request(user_id="b", payload={"n": 2}), validate=accept)

    assert h.ledger.spent_today("a") == 400
    assert h.ledger.spent_today("b") == 400
    assert h.ledger.spent_today() == 800


async def test_a_user_at_their_cap_is_stopped_before_any_provider_is_called() -> None:
    primary = FakeProvider("primary", [GOOD], estimated_cost_micro_inr=500)
    h = Harness(primary, caps=SpendCaps(per_user_daily_micro_inr=800, global_daily_micro_inr=10**9))

    await h.gateway.call(request(payload={"n": 1}), validate=accept)  # spends 400
    with pytest.raises(SpendCapExceededError) as caught:
        await h.gateway.call(request(payload={"n": 2}), validate=accept)  # 400 + 500 > 800

    assert caught.value.scope == "user"
    assert len(primary.calls) == 1
    # Another user is not affected.
    other = await h.gateway.call(request(user_id="user-2", payload={"n": 2}), validate=accept)
    assert other.provider == "primary"


async def test_the_global_cap_stops_everyone() -> None:
    h = Harness(
        FakeProvider("primary", [GOOD], estimated_cost_micro_inr=500),
        caps=SpendCaps(per_user_daily_micro_inr=10**9, global_daily_micro_inr=800),
    )

    await h.gateway.call(request(user_id="a"), validate=accept)
    with pytest.raises(SpendCapExceededError) as caught:
        await h.gateway.call(request(user_id="b", payload={"n": 2}), validate=accept)

    assert caught.value.scope == "global"


async def test_a_cheaper_fallback_is_used_when_the_primary_would_pass_the_cap() -> None:
    premium = FakeProvider("premium", [GOOD], estimated_cost_micro_inr=5_000)
    cheap = FakeProvider("cheap", [OTHER], estimated_cost_micro_inr=200)
    h = Harness(premium, cheap, caps=SpendCaps(1_000, 10**9))

    response = await h.gateway.call(request(), validate=accept)

    assert response.provider == "cheap"
    assert premium.calls == []
    assert h.outcomes() == [("premium", "over_spend_cap"), ("cheap", "success")]


async def test_failed_calls_cost_nothing() -> None:
    h = Harness(FakeProvider("primary", [DOWN]), FakeProvider("fallback", [DOWN]))
    with pytest.raises(AllProvidersFailedError):
        await h.gateway.call(request(), validate=accept)
    assert h.ledger.spent_today() == 0
    assert h.ledger.spent_today("user-1") == 0


async def test_concurrent_calls_cannot_overshoot_a_cap_together() -> None:
    hold = asyncio.Event()
    primary = FakeProvider("primary", [GOOD], estimated_cost_micro_inr=400, hold=hold)
    h = Harness(
        primary, caps=SpendCaps(per_user_daily_micro_inr=1_000, global_daily_micro_inr=10**9)
    )

    tasks = [
        asyncio.create_task(h.gateway.call(request(payload={"n": n}), validate=accept))
        for n in range(5)
    ]
    await asyncio.sleep(0)
    hold.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)

    succeeded = [r for r in results if not isinstance(r, BaseException)]
    blocked = [r for r in results if isinstance(r, SpendCapExceededError)]
    assert (len(succeeded), len(blocked)) == (2, 3)  # 2 x 400 fits under 1,000; a third does not
    assert h.ledger.spent_today("user-1") == 800


async def test_spending_exactly_up_to_the_cap_is_allowed() -> None:
    ledger = InMemorySpendLedger(SpendCaps(900, 10**9))
    await ledger.settle(await ledger.reserve("a", 400), 400)
    assert (await ledger.reserve("a", 500)).amount_micro_inr == 500
    with pytest.raises(SpendCapExceededError):
        await ledger.reserve("a", 1)


async def test_spend_resets_each_day() -> None:
    today = datetime.date(2000, 1, 1)
    ledger = InMemorySpendLedger(SpendCaps(500, 10**9), today=lambda: today)
    await ledger.settle(await ledger.reserve("a", 500), 500)
    with pytest.raises(SpendCapExceededError):
        await ledger.reserve("a", 1)
    today = datetime.date(2000, 1, 2)
    assert (await ledger.reserve("a", 500)).amount_micro_inr == 500


# --- caching by content hash --------------------------------------------------


async def test_identical_content_is_answered_from_the_cache_at_no_cost() -> None:
    primary = FakeProvider("primary", [GOOD])
    h = Harness(primary)

    first = await h.gateway.call(request(), validate=accept)
    # Same content from a different user, with the payload keys in another order.
    again = await h.gateway.call(
        request(user_id="user-2", payload={"style": "japandi", "budget": 150000}), validate=accept
    )

    assert len(primary.calls) == 1
    assert again.cached and again.output == first.output
    assert again.cost_micro_inr == 0
    assert h.ledger.spent_today() == 400
    assert h.outcomes() == [("primary", "success"), ("primary", "cache_hit")]


@pytest.mark.parametrize(
    "changes",
    [
        {"payload": {"budget": 150001, "style": "japandi"}},
        {"prompt_id": "brief_to_spec@2"},
        {"task": "designer"},
        {"blobs": (b"photo-bytes",)},
    ],
)
async def test_any_change_in_content_or_prompt_version_misses_the_cache(
    changes: dict[str, Any],
) -> None:
    primary = FakeProvider("primary", [GOOD])
    h = Harness(primary)

    await h.gateway.call(request(), validate=accept)
    await h.gateway.call(request(**changes), validate=accept)

    assert len(primary.calls) == 2


async def test_changing_a_pinned_model_version_misses_the_cache() -> None:
    cache = InMemoryResponseCache()
    for model in ("model-1", "model-2"):
        provider = FakeProvider("primary", [GOOD], model=model)
        gateway = ModelGateway(
            [provider], ledger=InMemorySpendLedger(ROOMY), cache=cache, call_log=InMemoryCallLog()
        )
        await gateway.call(request(), validate=accept)
        assert len(provider.calls) == 1


async def test_the_cache_can_be_skipped_for_one_call() -> None:
    primary = FakeProvider("primary", [GOOD])
    h = Harness(primary)
    await h.gateway.call(request(), validate=accept)
    await h.gateway.call(request(), validate=accept, use_cache=False)
    assert len(primary.calls) == 2


# --- concurrency --------------------------------------------------------------


async def test_calls_to_one_provider_never_exceed_its_concurrency_limit() -> None:
    hold = asyncio.Event()
    primary = FakeProvider("primary", [GOOD], max_concurrency=2, hold=hold)
    h = Harness(primary)

    tasks = [
        asyncio.create_task(h.gateway.call(request(payload={"n": n}), validate=accept))
        for n in range(6)
    ]
    for _ in range(5):
        await asyncio.sleep(0)
    assert primary.in_flight == 2
    hold.set()
    await asyncio.gather(*tasks)

    assert primary.peak_in_flight == 2
    assert len(primary.calls) == 6


# --- call logging -------------------------------------------------------------


async def test_every_attempt_is_logged_with_cost_and_latency() -> None:
    primary = FakeProvider("primary", [DOWN, GOOD], model="model-7")
    h = Harness(primary)

    await h.gateway.call(request(), validate=accept)

    failed, succeeded = h.log.entries
    assert (failed.outcome, failed.attempt, failed.error) == ("error", 1, "503 from provider")
    assert (succeeded.outcome, succeeded.attempt) == ("success", 2)
    assert (succeeded.provider, succeeded.model) == ("primary", "model-7")
    assert (succeeded.task, succeeded.prompt_id) == ("brief_to_spec", "brief_to_spec@1")
    assert succeeded.cost_micro_inr == 400
    assert succeeded.user_id == "user-1"
    assert succeeded.latency_ms >= 0


async def test_the_log_never_contains_prompt_content_or_model_output(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gateway = ModelGateway(
        [FakeProvider("primary", [ProviderResult({"reply": "SECRET-OUTPUT"})])],
        ledger=InMemorySpendLedger(ROOMY),
        call_log=JsonCallLog(),
    )
    with caplog.at_level(logging.INFO, logger="sajao_gateway.calls"):
        await gateway.call(
            request(payload={"note": "SECRET-INPUT"}, blobs=(b"SECRET-PHOTO",)), validate=accept
        )

    (line,) = caplog.messages
    entry = json.loads(line)
    assert entry["outcome"] == "success"
    assert len(entry["cache_key"]) == 64
    assert "SECRET" not in line


# --- construction -------------------------------------------------------------


def test_a_gateway_needs_a_chain_with_unique_provider_names() -> None:
    ledger = InMemorySpendLedger(ROOMY)
    with pytest.raises(ValueError, match="at least one provider"):
        ModelGateway([], ledger=ledger)
    with pytest.raises(ValueError, match="unique"):
        ModelGateway([FakeProvider("same", [GOOD]), FakeProvider("same", [GOOD])], ledger=ledger)
