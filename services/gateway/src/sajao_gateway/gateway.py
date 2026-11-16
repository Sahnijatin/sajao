"""The model gateway: the one path every model call goes through."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal

from sajao_gateway.breaker import CircuitBreaker
from sajao_gateway.cache import InMemoryResponseCache, ResponseCache
from sajao_gateway.errors import (
    AllProvidersFailedError,
    InvalidOutputError,
    ProviderError,
    SpendCapExceededError,
)
from sajao_gateway.log import CallLog, JsonCallLog
from sajao_gateway.spend import SpendLedger
from sajao_gateway.types import (
    CallRecord,
    ModelRequest,
    ModelResponse,
    Provider,
    ProviderResult,
    RetryPolicy,
    content_hash,
)

Validator = Callable[[ProviderResult], None]
Degraded = Callable[[ModelRequest], Awaitable[ProviderResult]]

DEGRADED_PROVIDER = "degraded"


class ModelGateway:
    """Routes a call through a chain of providers: primary first, then fallbacks.

    For each call the gateway:
      1. returns a cached response when the same content was answered before;
      2. skips providers whose circuit is open;
      3. reserves the estimated cost against the spend caps;
      4. limits concurrency per provider, retries with backoff, and times out;
      5. validates the output, treating an invalid one as a failure;
      6. logs every attempt with cost and latency;
      7. ends in the degraded mode, when one is given, so callers never stop suddenly.
    """

    def __init__(
        self,
        chain: Sequence[Provider],
        *,
        ledger: SpendLedger,
        cache: ResponseCache | None = None,
        call_log: CallLog | None = None,
        retry: RetryPolicy | None = None,
        breaker_failure_threshold: int = 5,
        breaker_cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if not chain:
            raise ValueError("The provider chain needs at least one provider")
        names = [provider.name for provider in chain]
        if len(set(names)) != len(names):
            raise ValueError("Provider names in a chain must be unique")
        self._chain = tuple(chain)
        self._chain_id = tuple(f"{provider.name}:{provider.model}" for provider in chain)
        self._ledger = ledger
        self._cache = cache or InMemoryResponseCache()
        self._log = call_log or JsonCallLog()
        self._retry = retry or RetryPolicy()
        self._clock = clock
        self._sleep = sleep
        self._jitter = jitter
        self._limits = {p.name: asyncio.Semaphore(p.max_concurrency) for p in chain}
        self._breakers = {
            p.name: CircuitBreaker(clock, breaker_failure_threshold, breaker_cooldown_seconds)
            for p in chain
        }

    async def call(
        self,
        request: ModelRequest,
        *,
        validate: Validator,
        degraded: Degraded | None = None,
        use_cache: bool = True,
    ) -> ModelResponse:
        """Run one model call.

        `validate` is required: every model output is checked before use. It
        raises InvalidOutputError to reject an output. `degraded` is the last
        step of the chain (rules instead of a model, a 3D render instead of a
        photo render); its result is not validated, cached or charged.
        """
        key = content_hash(request, self._chain_id)

        def record(outcome: Any, provider: Provider | None = None, **details: Any) -> None:
            self._log.record(
                CallRecord(
                    task=request.task,
                    modality=request.modality,
                    prompt_id=request.prompt_id,
                    cache_key=key,
                    user_id=request.user_id,
                    provider=provider.name if provider else details.pop("provider_name", None),
                    model=provider.model if provider else None,
                    outcome=outcome,
                    **details,
                )
            )

        if use_cache:
            cached = await self._cache.get(key)
            if cached is not None:
                record("cache_hit", provider_name=cached.provider)
                return ModelResponse(
                    cached.output, cached.blobs, cached.provider, cached.model, 0, cached=True
                )

        cap_hit: Literal["user", "global"] | None = None
        tried_a_provider = False
        for provider in self._chain:
            if request.modality not in provider.modalities:
                continue
            if not self._breakers[provider.name].allow():
                record("circuit_open", provider)
                continue
            try:
                reservation = await self._ledger.reserve(
                    request.user_id, provider.estimate_cost_micro_inr(request)
                )
            except SpendCapExceededError as error:
                # A cheaper fallback may still fit under the cap.
                cap_hit = cap_hit or error.scope
                self._breakers[provider.name].cancel_trial()
                record("over_spend_cap", provider, error=error.scope)
                continue

            tried_a_provider = True
            result = await self._call_provider(provider, request, validate, record)
            if result is None:
                await self._ledger.settle(reservation, 0)
                self._breakers[provider.name].record_failure()
                continue
            await self._ledger.settle(reservation, result.cost_micro_inr)
            self._breakers[provider.name].record_success()
            response = ModelResponse(
                result.output, result.blobs, provider.name, provider.model, result.cost_micro_inr
            )
            if use_cache:
                await self._cache.set(key, response)
            return response

        if cap_hit is not None and not tried_a_provider:
            # Nothing ran only because of money: the caller queues the work.
            raise SpendCapExceededError(cap_hit)
        if degraded is not None:
            result = await degraded(request)
            record("degraded", provider_name=DEGRADED_PROVIDER)
            return ModelResponse(
                result.output, result.blobs, DEGRADED_PROVIDER, DEGRADED_PROVIDER, 0, degraded=True
            )
        raise AllProvidersFailedError(f"No provider could complete {request.task}")

    async def _call_provider(
        self,
        provider: Provider,
        request: ModelRequest,
        validate: Validator,
        record: Callable[..., None],
    ) -> ProviderResult | None:
        """Call one provider with retries. Returns None when it could not answer.

        A provider may declare `timeout_seconds` (a GPU job that runs for minutes)
        and `max_attempts` (an expensive job retried by its durable step instead);
        otherwise the gateway's retry policy applies.
        """
        timeout = getattr(provider, "timeout_seconds", None) or self._retry.timeout_seconds
        attempts = min(
            self._retry.max_attempts,
            getattr(provider, "max_attempts", None) or self._retry.max_attempts,
        )
        for attempt in range(1, attempts + 1):
            started = self._clock()
            retryable = True
            outcome = "error"
            try:
                async with self._limits[provider.name]:
                    async with asyncio.timeout(timeout):
                        result = await provider.call(request)
                validate(result)
            except InvalidOutputError as error:
                outcome, message = "invalid_output", str(error)
            except ProviderError as error:
                retryable, message = error.retryable, str(error)
            except TimeoutError:
                message = "timeout"
            except Exception as error:
                # A provider SDK can raise anything; one bad provider must not stop the chain.
                message = type(error).__name__
            else:
                record(
                    "success",
                    provider,
                    attempt=attempt,
                    latency_ms=self._elapsed_ms(started),
                    cost_micro_inr=result.cost_micro_inr,
                )
                return result

            record(
                outcome,
                provider,
                attempt=attempt,
                latency_ms=self._elapsed_ms(started),
                error=message,
            )
            if not retryable or attempt == attempts:
                return None
            await self._sleep(self._backoff(attempt))
        return None

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter."""
        doubled: float = self._retry.base_delay_seconds * 2 ** (attempt - 1)
        return min(self._retry.max_delay_seconds, doubled) * self._jitter()

    def _elapsed_ms(self, started: float) -> float:
        return round((self._clock() - started) * 1000, 1)
