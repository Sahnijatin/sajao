import os
import time
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from sajao_api.auth import InvalidTokenError, JwksTokenVerifier
from sajao_api.idempotency import InMemoryIdempotencyStore
from sajao_api.main import create_app
from sajao_api.settings import Settings

from .conftest import Calls, add_test_routes

ISSUER = "https://auth.test/auth/v1"
KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())
VERIFIER = JwksTokenVerifier("unused", ISSUER, key_for=lambda _token: KEY.public_key())


def token(key: Any = KEY, algorithm: str = "ES256", **changes: Any) -> str:
    claims: dict[str, Any] = {
        "sub": "user-1",
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 600,
        "is_anonymous": False,
        **changes,
    }
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm=algorithm)


def client(calls: Calls | None = None, verifier: Any = VERIFIER) -> httpx.AsyncClient:
    app = create_app(Settings(), InMemoryIdempotencyStore(), verifier)
    if calls is not None:
        add_test_routes(app, calls)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://api.test")


def bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


async def test_a_signed_in_user_is_recognised() -> None:
    async with client() as api:
        response = await api.get("/v1/me", headers=bearer(token()))
    assert response.status_code == 200
    assert response.json() == {"user_id": "user-1", "is_guest": False}


async def test_a_guest_has_a_real_identity() -> None:
    async with client() as api:
        response = await api.get("/v1/me", headers=bearer(token(sub="guest-9", is_anonymous=True)))
    assert response.json() == {"user_id": "guest-9", "is_guest": True}


async def test_public_endpoints_need_no_token_but_account_endpoints_do() -> None:
    async with client() as api:
        assert (await api.get("/v1/health")).status_code == 200
        response = await api.get("/v1/me")
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "not_authenticated", "message": "This request needs an access token."}
    }


@pytest.mark.parametrize(
    "bad",
    [
        token(key=OTHER_KEY),  # signed by someone else
        token(exp=int(time.time()) - 5),  # expired
        token(aud="anon"),  # wrong audience
        token(iss="https://elsewhere.test"),  # wrong issuer
        token(sub=None),  # no subject
        token(exp=None),  # never expires
        token(key="a-shared-secret-that-is-long-enough-for-hs256", algorithm="HS256"),
        "not-a-token",
    ],
    ids=["wrong-key", "expired", "audience", "issuer", "no-sub", "no-exp", "hs256", "garbage"],
)
async def test_an_invalid_token_is_rejected_everywhere_even_on_public_endpoints(bad: str) -> None:
    with pytest.raises(InvalidTokenError):
        VERIFIER.verify(bad)
    async with client() as api:
        for path in ("/v1/me", "/v1/health"):
            response = await api.get(path, headers=bearer(bad))
            assert response.status_code == 401
            assert response.json()["error"] == {
                "code": "invalid_token",
                "message": "The access token is not valid.",
            }


async def test_an_unsigned_token_is_rejected() -> None:
    unsigned = jwt.encode(
        {"sub": "user-1", "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 600},
        key="",
        algorithm="none",
    )
    async with client() as api:
        assert (await api.get("/v1/me", headers=bearer(unsigned))).status_code == 401


async def test_other_authorization_schemes_are_rejected() -> None:
    async with client() as api:
        response = await api.get("/v1/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401


async def test_tokens_are_rejected_when_auth_is_not_configured() -> None:
    async with client(verifier=None) as api:
        assert (await api.get("/v1/me", headers=bearer(token()))).status_code == 401


async def test_an_unreachable_key_service_fails_closed() -> None:
    def unreachable(_token: str) -> Any:
        raise ConnectionError("key service down")

    async with client(verifier=JwksTokenVerifier("unused", ISSUER, key_for=unreachable)) as api:
        response = await api.get("/v1/me", headers=bearer(token()))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_unavailable"


async def test_idempotency_keys_belong_to_the_caller() -> None:
    calls = Calls()
    key = {"Idempotency-Key": "same-key-1"}
    async with client(calls) as api:
        a1 = await api.post(
            "/v1/test/things", json={"name": "sofa"}, headers={**key, **bearer(token(sub="a"))}
        )
        b1 = await api.post(
            "/v1/test/things", json={"name": "sofa"}, headers={**key, **bearer(token(sub="b"))}
        )
        a2 = await api.post(
            "/v1/test/things", json={"name": "sofa"}, headers={**key, **bearer(token(sub="a"))}
        )
    # Two users with the same key each get their own run; a retry replays only its own.
    assert calls.created == 2
    assert (a1.json()["number"], b1.json()["number"], a2.json()["number"]) == (1, 2, 1)
    assert a2.headers["idempotency-replayed"] == "true"


def test_auth_settings_are_set_together_and_required_outside_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAJAO_AUTH_JWKS_URL", "https://auth.test/jwks.json")
    with pytest.raises(ValueError, match="must be set together"):
        Settings()
    monkeypatch.delenv("SAJAO_AUTH_JWKS_URL")
    monkeypatch.setenv("SAJAO_ENVIRONMENT", "production")
    monkeypatch.setenv("SAJAO_DATABASE_URL", "postgresql://unused")
    with pytest.raises(ValueError, match="SAJAO_AUTH_JWKS_URL is required"):
        Settings()


LOCAL_AUTH_URL = os.environ.get("SAJAO_TEST_SUPABASE_URL") or None
LOCAL_ANON_KEY = os.environ.get("SAJAO_TEST_SUPABASE_ANON_KEY") or None


@pytest.mark.skipif(LOCAL_AUTH_URL is None, reason="SAJAO_TEST_SUPABASE_URL is not set")
async def test_a_real_guest_session_from_the_local_stack_is_accepted() -> None:
    assert LOCAL_AUTH_URL is not None and LOCAL_ANON_KEY is not None
    async with httpx.AsyncClient() as http:
        signup = await http.post(
            f"{LOCAL_AUTH_URL}/auth/v1/signup", headers={"apikey": LOCAL_ANON_KEY}, json={}
        )
    session = signup.json()
    settings = Settings(
        auth_jwks_url=f"{LOCAL_AUTH_URL}/auth/v1/.well-known/jwks.json",
        auth_issuer=f"{LOCAL_AUTH_URL}/auth/v1",
    )
    transport = httpx.ASGITransport(app=create_app(settings, InMemoryIdempotencyStore()))
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as api:
        response = await api.get("/v1/me", headers=bearer(session["access_token"]))
    assert response.status_code == 200
    assert response.json() == {"user_id": session["user"]["id"], "is_guest": True}
