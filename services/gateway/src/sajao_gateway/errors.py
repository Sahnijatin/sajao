from typing import Literal


class GatewayError(Exception):
    """Base class for everything the gateway raises."""


class ProviderError(GatewayError):
    """A provider call failed. `retryable` says whether trying again can help."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class InvalidOutputError(GatewayError):
    """Raise from a validator when a model's output fails its check."""


class SpendCapExceededError(GatewayError):
    """The call would pass a spend cap. Queue the work with an honest message; do not fail it."""

    def __init__(self, scope: Literal["user", "global"]) -> None:
        super().__init__(f"{scope} spend cap reached")
        self.scope = scope


class AllProvidersFailedError(GatewayError):
    """Every provider in the chain failed and there is no degraded mode."""
