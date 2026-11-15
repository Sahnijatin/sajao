"""Circuit breaker: stop calling a provider that keeps failing, then probe it."""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class CircuitBreaker:
    """Closed until `failure_threshold` failures in a row, then open for
    `cooldown_seconds`. After that one trial call is let through: success
    closes the circuit, failure opens it again.
    """

    clock: Callable[[], float]
    failure_threshold: int = 5
    cooldown_seconds: float = 30.0
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _trial_in_flight: bool = field(default=False, init=False)

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if self.clock() - self._opened_at < self.cooldown_seconds or self._trial_in_flight:
            return False
        self._trial_in_flight = True
        return True

    def cancel_trial(self) -> None:
        """The allowed call never reached the provider, so it proves nothing."""
        self._trial_in_flight = False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._trial_in_flight = False

    def record_failure(self) -> None:
        self._failures += 1
        if self._trial_in_flight or self._failures >= self.failure_threshold:
            self._opened_at = self.clock()
        self._trial_in_flight = False
