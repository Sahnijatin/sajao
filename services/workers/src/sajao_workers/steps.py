"""Durable pipeline steps.

A step is a pure function of its input blobs and params. Its key is the hash of
the step name, version, input blob digests and params, so:

- the same work never runs twice: a stored result is returned at no cost;
- a job resumes where it stopped: finished steps are found by key;
- a failed step retries alone and stores nothing until it succeeds;
- a step already running elsewhere is not started again while its lease holds.

Blobs are content addressed. The result manifest is written last, after every
output blob, so a crash mid-step leaves no half result behind.
"""

import asyncio
import hashlib
import json
import os
import random
import tempfile
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class StepFailedError(Exception):
    """The step could not finish. Nothing was stored; running it again starts over."""


class NonRetryableStepError(Exception):
    """Raised by a step when retrying can never help, such as invalid input."""


class StepBusyError(Exception):
    """Another worker holds the lease on this step. Try again later."""


@dataclass(frozen=True)
class StepOutput:
    """What a step returns: named output files, small JSON metadata, and what it spent.

    `refs` names blobs already in the store (written by a GPU function), so large
    outputs such as a splat are recorded without passing through this process.
    """

    files: Mapping[str, bytes] = field(default_factory=dict)
    refs: Mapping[str, str] = field(default_factory=dict)
    meta: Mapping[str, Any] = field(default_factory=dict)
    gpu_seconds: float = 0.0
    cost_micro_inr: int = 0


@dataclass(frozen=True)
class StepContext:
    store: "ArtifactStore"
    inputs: Mapping[str, str]  # input name to blob digest
    params: Mapping[str, Any]

    def read(self, name: str) -> bytes:
        return self.store.read_blob(self.inputs[name])


@dataclass(frozen=True)
class Step:
    name: str
    version: int  # Bump when the step's code or pinned models change.
    run: Callable[[StepContext], Awaitable[StepOutput]]


@dataclass(frozen=True)
class StepResult:
    key: str
    outputs: Mapping[str, str]  # output name to blob digest
    meta: Mapping[str, Any]
    cached: bool
    gpu_seconds: float  # Spent by this call: zero when the result was stored already.
    cost_micro_inr: int


class ArtifactStore(Protocol):
    def put_blob(self, data: bytes) -> str: ...
    def read_blob(self, digest: str) -> bytes: ...
    def has_blob(self, digest: str) -> bool: ...
    def read_manifest(self, key: str) -> Mapping[str, Any] | None: ...
    def write_manifest(self, key: str, manifest: Mapping[str, Any]) -> None: ...
    def acquire_lease(self, key: str, expires_at: float) -> bool: ...
    def lease_expiry(self, key: str) -> float | None: ...
    def release_lease(self, key: str) -> None: ...


class LocalArtifactStore:
    """Artifacts on a filesystem: a local disk in tests, a mounted volume on workers.

    Writes go to a temporary file and are renamed into place, so readers never
    see a partial file. Leases use exclusive create. On a network volume that is
    only eventually consistent across containers, two workers can rarely both
    take a lease; the step then runs twice and stores the same result, which
    costs money but never corrupts anything.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def _blob_path(self, digest: str) -> Path:
        return self.root / "blobs" / digest[:2] / digest

    def put_blob(self, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = self._blob_path(digest)
        if not path.exists():
            _write_atomic(path, data)
        return digest

    def read_blob(self, digest: str) -> bytes:
        return self._blob_path(digest).read_bytes()

    def has_blob(self, digest: str) -> bool:
        return self._blob_path(digest).exists()

    def delete_blob(self, digest: str) -> None:
        """Remove a blob; missing is fine. Only for stores that hold copies (the GPU
        bridge's), never for a step store whose manifests point at its blobs."""
        self._blob_path(digest).unlink(missing_ok=True)

    def read_manifest(self, key: str) -> Mapping[str, Any] | None:
        path = self.root / "steps" / f"{key}.json"
        if not path.exists():
            return None
        manifest: Mapping[str, Any] = json.loads(path.read_text())
        return manifest

    def write_manifest(self, key: str, manifest: Mapping[str, Any]) -> None:
        _write_atomic(self.root / "steps" / f"{key}.json", json.dumps(manifest).encode())

    def acquire_lease(self, key: str, expires_at: float) -> bool:
        path = self.root / "leases" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x") as file:
                file.write(str(expires_at))
            return True
        except FileExistsError:
            return False

    def lease_expiry(self, key: str) -> float | None:
        try:
            return float((self.root / "leases" / key).read_text())
        except (FileNotFoundError, ValueError):
            return None

    def release_lease(self, key: str) -> None:
        (self.root / "leases" / key).unlink(missing_ok=True)


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(handle, "wb") as file:
        file.write(data)
    os.replace(temporary, path)


class StepRunner:
    def __init__(
        self,
        store: ArtifactStore,
        *,
        max_attempts: int = 3,
        base_delay_seconds: float = 2.0,
        lease_seconds: float = 3600.0,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.store = store
        self._max_attempts = max_attempts
        self._base_delay = base_delay_seconds
        self._lease_seconds = lease_seconds
        self._clock = clock
        self._sleep = sleep

    @staticmethod
    def key(step: Step, inputs: Mapping[str, str], params: Mapping[str, Any]) -> str:
        header = {"step": step.name, "version": step.version, "inputs": inputs, "params": params}
        encoded = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    async def run(
        self, step: Step, inputs: Mapping[str, str], params: Mapping[str, Any]
    ) -> StepResult:
        key = self.key(step, inputs, params)
        stored = self.store.read_manifest(key)
        if stored is not None:
            return StepResult(key, stored["outputs"], stored["meta"], True, 0.0, 0)

        missing = [name for name, digest in inputs.items() if not self.store.has_blob(digest)]
        if missing:
            raise StepFailedError(f"{step.name}: missing input {', '.join(sorted(missing))}")

        self._take_lease(step, key)
        try:
            output = await self._run_with_retries(step, StepContext(self.store, inputs, params))
            missing = sorted(n for n, d in output.refs.items() if not self.store.has_blob(d))
            if missing:
                raise StepFailedError(
                    f"{step.name}: output {', '.join(missing)} is not in the store"
                )
            outputs = {name: self.store.put_blob(data) for name, data in output.files.items()}
            outputs.update(output.refs)
            manifest = {
                "step": step.name,
                "version": step.version,
                "outputs": outputs,
                "meta": dict(output.meta),
                "gpu_seconds": output.gpu_seconds,
                "cost_micro_inr": output.cost_micro_inr,
            }
            self.store.write_manifest(key, manifest)
        finally:
            self.store.release_lease(key)
        return StepResult(
            key, outputs, output.meta, False, output.gpu_seconds, output.cost_micro_inr
        )

    def _take_lease(self, step: Step, key: str) -> None:
        expires_at = self._clock() + self._lease_seconds
        if self.store.acquire_lease(key, expires_at):
            return
        held_until = self.store.lease_expiry(key)
        if held_until is not None and held_until > self._clock():
            raise StepBusyError(f"{step.name} is already running")
        # The holder died without releasing: take the lease over.
        self.store.release_lease(key)
        if not self.store.acquire_lease(key, expires_at):
            raise StepBusyError(f"{step.name} is already running")

    async def _run_with_retries(self, step: Step, context: StepContext) -> StepOutput:
        for attempt in range(1, self._max_attempts + 1):
            try:
                return await step.run(context)
            except NonRetryableStepError as error:
                raise StepFailedError(f"{step.name}: {error}") from error
            except Exception as error:
                if attempt == self._max_attempts:
                    raise StepFailedError(f"{step.name}: {error}") from error
                await self._sleep(self._base_delay * 2 ** (attempt - 1) * random.random())  # noqa: S311
        raise AssertionError("unreachable")
