"""The shapes every model call uses, whatever the provider."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Modality = Literal["text", "vision", "image"]

# Money inside the gateway is whole micro-rupees (1 rupee = 1,000,000), so a
# call that costs a fraction of a paisa still adds up exactly.
MICRO_INR_PER_RUPEE = 1_000_000


@dataclass(frozen=True)
class ModelRequest:
    """One model call. `payload` must be JSON data; images and other bytes go in `blobs`."""

    task: str  # What the call is for, for example "brief_to_spec". Used in logs and cost reports.
    modality: Modality
    prompt_id: str  # The pinned prompt name and version, for example "brief_to_spec@3".
    payload: Mapping[str, Any]
    blobs: tuple[bytes, ...] = ()
    user_id: str | None = None  # None for offline work such as catalog batches.


@dataclass(frozen=True)
class ProviderResult:
    """What a provider returns, before the gateway validates it."""

    output: Mapping[str, Any]
    blobs: tuple[bytes, ...] = ()
    cost_micro_inr: int = 0


@dataclass(frozen=True)
class ModelResponse:
    output: Mapping[str, Any]
    blobs: tuple[bytes, ...]
    provider: str
    model: str
    cost_micro_inr: int
    cached: bool = False
    degraded: bool = False  # True when the chain ended in the degraded mode.


class Provider(Protocol):
    """A model behind one provider, at one pinned version."""

    name: str
    model: str  # Pinned model identifier, including its version.
    modalities: frozenset[Modality]
    max_concurrency: int

    def estimate_cost_micro_inr(self, request: ModelRequest) -> int:
        """An upper bound on what this call can cost, checked against spend caps."""
        ...

    async def call(self, request: ModelRequest) -> ProviderResult: ...


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class CallRecord:
    """One line in the call log. Holds hashes and numbers, never prompts or outputs."""

    task: str
    modality: Modality
    prompt_id: str
    cache_key: str
    user_id: str | None
    provider: str | None
    model: str | None
    outcome: Literal[
        "success",
        "cache_hit",
        "error",
        "invalid_output",
        "circuit_open",
        "over_spend_cap",
        "degraded",
    ]
    attempt: int = 0
    latency_ms: float = 0.0
    cost_micro_inr: int = 0
    error: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


def content_hash(request: ModelRequest, chain: tuple[str, ...]) -> str:
    """Cache key: the request's content plus the pinned models that may answer it.

    The user is not part of the key, so identical work is shared. Changing a
    prompt version or a model version changes the key.
    """
    digest = hashlib.sha256()
    header = {
        "task": request.task,
        "modality": request.modality,
        "prompt_id": request.prompt_id,
        "payload": request.payload,
        "chain": chain,
    }
    digest.update(json.dumps(header, sort_keys=True, separators=(",", ":")).encode())
    for blob in request.blobs:
        digest.update(b"\x00")
        digest.update(hashlib.sha256(blob).digest())
    return digest.hexdigest()
