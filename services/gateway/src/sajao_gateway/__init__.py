"""Sajao model gateway: the one path every model call goes through."""

from sajao_gateway.cache import InMemoryResponseCache, ResponseCache
from sajao_gateway.errors import (
    AllProvidersFailedError,
    GatewayError,
    InvalidOutputError,
    ProviderError,
    SpendCapExceededError,
)
from sajao_gateway.gateway import ModelGateway
from sajao_gateway.log import CallLog, InMemoryCallLog, JsonCallLog
from sajao_gateway.spend import InMemorySpendLedger, SpendCaps, SpendLedger
from sajao_gateway.types import (
    MICRO_INR_PER_RUPEE,
    CallRecord,
    ModelRequest,
    ModelResponse,
    Provider,
    ProviderResult,
    RetryPolicy,
)

__version__ = "0.0.0"

__all__ = [
    "MICRO_INR_PER_RUPEE",
    "AllProvidersFailedError",
    "CallLog",
    "CallRecord",
    "GatewayError",
    "InMemoryCallLog",
    "InMemoryResponseCache",
    "InMemorySpendLedger",
    "InvalidOutputError",
    "JsonCallLog",
    "ModelGateway",
    "ModelRequest",
    "ModelResponse",
    "Provider",
    "ProviderError",
    "ProviderResult",
    "ResponseCache",
    "RetryPolicy",
    "SpendCapExceededError",
    "SpendCaps",
    "SpendLedger",
]
