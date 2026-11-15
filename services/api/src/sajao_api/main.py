"""The Sajao API: a stateless modular monolith behind a versioned /v1."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from starlette.types import Scope

from sajao_api import __version__, v1
from sajao_api.auth import JwksTokenVerifier, TokenVerifier
from sajao_api.errors import ApiError, api_error_handler
from sajao_api.idempotency import (
    IdempotencyStore,
    InMemoryIdempotencyStore,
    PostgresIdempotencyStore,
)
from sajao_api.logging import configure_logging
from sajao_api.middleware.app_version import MinimumAppVersionMiddleware
from sajao_api.middleware.auth import AuthMiddleware
from sajao_api.middleware.idempotency import IdempotencyMiddleware
from sajao_api.middleware.request_context import RequestContextMiddleware
from sajao_api.settings import Settings


def _key_owner(scope: Scope) -> str:
    """Idempotency keys belong to the caller, so users never see each other's responses."""
    principal = scope.get("state", {}).get("principal")
    return principal.user_id if principal is not None else "anonymous"


def create_app(
    settings: Settings | None = None,
    idempotency_store: IdempotencyStore | None = None,
    token_verifier: TokenVerifier | None = None,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    if token_verifier is None and settings.auth_jwks_url and settings.auth_issuer:
        token_verifier = JwksTokenVerifier(settings.auth_jwks_url, settings.auth_issuer)

    pool: AsyncConnectionPool | None = None
    store = idempotency_store
    if store is None:
        if settings.database_url is not None:
            # prepare_threshold=None: safe behind a transaction-mode connection pooler.
            pool = AsyncConnectionPool(
                settings.database_url.get_secret_value(),
                open=False,
                min_size=1,
                max_size=5,
                kwargs={"prepare_threshold": None, "autocommit": True},
            )
            store = PostgresIdempotencyStore(pool)
        else:
            store = InMemoryIdempotencyStore()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if pool is not None:
            await pool.open()
        try:
            yield
        finally:
            if pool is not None:
                await pool.close()

    app = FastAPI(
        title="Sajao API",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs" if settings.environment == "dev" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.include_router(v1.router)
    app.add_exception_handler(ApiError, api_error_handler)

    # Added innermost first: the request id wraps everything else.
    app.add_middleware(
        IdempotencyMiddleware,
        store=store,
        ttl_seconds=settings.idempotency_ttl_seconds,
        in_progress_seconds=settings.idempotency_in_progress_seconds,
        scope_for=_key_owner,
    )
    app.add_middleware(AuthMiddleware, verifier=token_verifier)
    app.add_middleware(MinimumAppVersionMiddleware, minimum=settings.min_app_version)
    app.add_middleware(RequestContextMiddleware)
    return app
