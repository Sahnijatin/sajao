"""Verify the bearer token, when one is sent, before anything else runs.

Requests without a token pass through as anonymous; endpoints that need a
caller use the `current_user` dependency. A token that is present but
invalid is always rejected, so a client never silently becomes anonymous.
"""

import asyncio

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from sajao_api.auth import InvalidTokenError, TokenVerifier
from sajao_api.errors import error_response
from sajao_api.logging import get_logger


class AuthMiddleware:
    def __init__(self, app: ASGIApp, verifier: TokenVerifier | None) -> None:
        self.app = app
        self.verifier = verifier

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        header = Headers(scope=scope).get("authorization")
        if header is None:
            await self.app(scope, receive, send)
            return

        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token or self.verifier is None:
            await self._reject(scope, receive, send, "malformed_or_unsupported")
            return
        try:
            # Verification may fetch signing keys over the network, so keep it off the loop.
            principal = await asyncio.to_thread(self.verifier.verify, token)
        except InvalidTokenError as error:
            await self._reject(scope, receive, send, str(error))
            return
        except Exception as error:
            # The key service is unreachable: fail closed, and say it is our side.
            get_logger().error("auth_keys_unavailable", error=type(error).__name__)
            response = error_response(
                503, "auth_unavailable", "Sign-in checks are unavailable. Try again shortly."
            )
            await response(scope, receive, send)
            return

        scope.setdefault("state", {})["principal"] = principal
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, reason: str) -> None:
        # The reason goes to logs only; the client learns nothing about why.
        get_logger().warning("token_rejected", reason=reason)
        response = error_response(401, "invalid_token", "The access token is not valid.")
        await response(scope, receive, send)
