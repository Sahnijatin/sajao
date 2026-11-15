"""Who is calling: verify the access token issued by the auth service.

Tokens are signed with the auth service's private key and verified here
against its published public keys (JWKS). Guests have a real user id too;
`is_guest` is true until they sign in.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import jwt
from fastapi import Request

from sajao_api.errors import ApiError

# Asymmetric algorithms only. A shared-secret or unsigned token is never accepted.
ALGORITHMS = ("ES256", "RS256")
AUDIENCE = "authenticated"


@dataclass(frozen=True)
class Principal:
    user_id: str
    is_guest: bool


class InvalidTokenError(Exception):
    pass


class TokenVerifier(Protocol):
    def verify(self, token: str) -> Principal:
        """Return who the token belongs to, or raise InvalidTokenError."""
        ...


class JwksTokenVerifier:
    def __init__(
        self, jwks_url: str, issuer: str, key_for: Callable[[str], Any] | None = None
    ) -> None:
        self._issuer = issuer
        if key_for is None:
            client = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=600, timeout=5)
            key_for = lambda token: client.get_signing_key_from_jwt(token).key  # noqa: E731
        self._key_for = key_for

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(
                token,
                self._key_for(token),
                algorithms=list(ALGORITHMS),
                audience=AUDIENCE,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as error:
            raise InvalidTokenError(type(error).__name__) from error
        return Principal(user_id=claims["sub"], is_guest=claims.get("is_anonymous") is True)


def current_user(request: Request) -> Principal:
    """FastAPI dependency for endpoints that need a caller. Guests count."""
    principal: Principal | None = request.scope.get("state", {}).get("principal")
    if principal is None:
        raise ApiError(401, "not_authenticated", "This request needs an access token.")
    return principal
