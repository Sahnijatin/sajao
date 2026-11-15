"""Call log: one record per attempt, with cost and latency."""

import dataclasses
import json
import logging
from typing import Protocol

from sajao_gateway.types import CallRecord


class CallLog(Protocol):
    def record(self, entry: CallRecord) -> None: ...


class JsonCallLog:
    """Writes each record as one JSON line through the standard logger."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("sajao_gateway.calls")

    def record(self, entry: CallRecord) -> None:
        level = logging.INFO if entry.outcome in ("success", "cache_hit") else logging.WARNING
        self._logger.log(level, json.dumps(dataclasses.asdict(entry), sort_keys=True))


class InMemoryCallLog:
    def __init__(self) -> None:
        self.entries: list[CallRecord] = []

    def record(self, entry: CallRecord) -> None:
        self.entries.append(entry)
