"""Idempotency-Key middleware for every write request."""

import hashlib
import re
from collections.abc import Callable

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sajao_api.errors import error_response
from sajao_api.idempotency import IdempotencyStore, Outcome, StoredResponse

IDEMPOTENCY_HEADER = "idempotency-key"
REPLAYED_HEADER = "idempotency-replayed"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MAX_BODY_BYTES = 1024 * 1024  # Media goes straight to object storage, never through here.

_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
# Per-response headers that must not be replayed from storage.
_NOT_STORED = frozenset({"x-request-id", "date", "server", "content-length"})


def _anonymous(_scope: Scope) -> str:
    return "anonymous"


class BodyTooLargeError(Exception):
    pass


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            return b"".join(chunks)
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise BodyTooLargeError
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)


class IdempotencyMiddleware:
    """Runs each write once per key and replays the stored response on retries.

    `scope_for` names who owns a key, so two users can never see each other's
    responses. It becomes the user id once authentication is in place.
    """

    def __init__(
        self,
        app: ASGIApp,
        store: IdempotencyStore,
        ttl_seconds: int,
        in_progress_seconds: int,
        scope_for: Callable[[Scope], str] = _anonymous,
    ) -> None:
        self.app = app
        self.store = store
        self.ttl_seconds = ttl_seconds
        self.in_progress_seconds = in_progress_seconds
        self.scope_for = scope_for

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in WRITE_METHODS:
            await self.app(scope, receive, send)
            return

        key = Headers(scope=scope).get(IDEMPOTENCY_HEADER)
        if key is None or not _KEY.match(key):
            response = error_response(
                400,
                "idempotency_key_required",
                "Write requests need an Idempotency-Key header of 8 to 128 characters.",
            )
            await response(scope, receive, send)
            return

        try:
            body = await _read_body(receive)
        except BodyTooLargeError:
            await error_response(413, "body_too_large", "Request body is too large.")(
                scope, receive, send
            )
            return

        owner = self.scope_for(scope)
        fingerprint = hashlib.sha256(
            b"\n".join(
                [scope["method"].encode(), scope["path"].encode(), scope["query_string"], body]
            )
        ).hexdigest()
        reservation = await self.store.reserve(owner, key, fingerprint, self.in_progress_seconds)

        if reservation.outcome is Outcome.MISMATCH:
            await error_response(
                422,
                "idempotency_key_reused",
                "This Idempotency-Key was already used for a different request.",
            )(scope, receive, send)
            return
        if reservation.outcome is Outcome.IN_PROGRESS:
            await error_response(
                409,
                "request_in_progress",
                "A request with this Idempotency-Key is still running. Retry shortly.",
            )(scope, receive, send)
            return
        if reservation.outcome is Outcome.COMPLETED and reservation.response is not None:
            await self._replay(reservation.response, send)
            return

        await self._run_once(scope, body, owner, key, send)

    async def _run_once(self, scope: Scope, body: bytes, owner: str, key: str, send: Send) -> None:
        delivered = False

        async def replay_body() -> Message:
            nonlocal delivered
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        captured: list[Message] = []

        async def capture(message: Message) -> None:
            captured.append(message)

        try:
            await self.app(scope, replay_body, capture)
        except BaseException:
            # The handler crashed: nothing to replay, so let a retry run it again.
            await self.store.release(owner, key)
            raise

        start = next((m for m in captured if m["type"] == "http.response.start"), None)
        if start is None:
            await self.store.release(owner, key)
            return
        status_code: int = start["status"]
        if status_code >= 500:
            # Server errors are not final answers. A retry should try again.
            await self.store.release(owner, key)
        else:
            headers = [
                (name.decode("latin-1"), value.decode("latin-1"))
                for name, value in start.get("headers", [])
                if name.decode("latin-1").lower() not in _NOT_STORED
            ]
            payload = b"".join(
                m.get("body", b"") for m in captured if m["type"] == "http.response.body"
            )
            await self.store.complete(
                owner, key, StoredResponse(status_code, headers, payload), self.ttl_seconds
            )
        for message in captured:
            await send(message)

    @staticmethod
    async def _replay(stored: StoredResponse, send: Send) -> None:
        headers = [
            (name.encode("latin-1"), value.encode("latin-1")) for name, value in stored.headers
        ]
        headers.append((b"content-length", str(len(stored.body)).encode()))
        headers.append((REPLAYED_HEADER.encode(), b"true"))
        await send(
            {"type": "http.response.start", "status": stored.status_code, "headers": headers}
        )
        await send({"type": "http.response.body", "body": stored.body})
