"""The Sajao API: a stateless modular monolith behind a versioned /v1."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from starlette.types import Scope

from sajao_api import __version__, v1
from sajao_api.accounts import AccountStore, InMemoryAccountStore, PostgresAccountStore
from sajao_api.auth import JwksTokenVerifier, TokenVerifier
from sajao_api.captures import CaptureStore, InMemoryCaptureStore, PostgresCaptureStore
from sajao_api.clicks import ClickStore, InMemoryClickStore, PostgresClickStore
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
from sajao_api.pipeline import ModalLauncher, PipelineLauncher, RecordingLauncher
from sajao_api.rooms import InMemoryRoomStore, PostgresRoomStore, RoomStore
from sajao_api.settings import Settings
from sajao_api.storage import ObjectStorage, S3ObjectStorage


def _key_owner(scope: Scope) -> str:
    """Idempotency keys belong to the caller, so users never see each other's responses."""
    principal = scope.get("state", {}).get("principal")
    return principal.user_id if principal is not None else "anonymous"


def create_app(
    settings: Settings | None = None,
    idempotency_store: IdempotencyStore | None = None,
    token_verifier: TokenVerifier | None = None,
    storage: ObjectStorage | None = None,
    capture_store: CaptureStore | None = None,
    room_store: RoomStore | None = None,
    pipeline: PipelineLauncher | None = None,
    account_store: AccountStore | None = None,
    click_store: ClickStore | None = None,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    if token_verifier is None and settings.auth_jwks_url and settings.auth_issuer:
        token_verifier = JwksTokenVerifier(settings.auth_jwks_url, settings.auth_issuer)

    pool: AsyncConnectionPool | None = None
    store = idempotency_store
    stores = (store, capture_store, room_store, account_store, click_store)
    if any(given is None for given in stores) and settings.database_url is not None:
        # prepare_threshold=None: safe behind a transaction-mode connection pooler.
        pool = AsyncConnectionPool(
            settings.database_url.get_secret_value(),
            open=False,
            min_size=1,
            max_size=5,
            kwargs={"prepare_threshold": None, "autocommit": True},
        )
    if store is None:
        store = PostgresIdempotencyStore(pool) if pool is not None else InMemoryIdempotencyStore()
    if capture_store is None:
        capture_store = PostgresCaptureStore(pool) if pool is not None else InMemoryCaptureStore()

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
    if (
        storage is None
        and settings.storage_endpoint
        and settings.storage_region
        and settings.storage_bucket
        and settings.storage_access_key_id
        and settings.storage_secret_access_key
    ):
        endpoint, region, bucket = (
            settings.storage_endpoint,
            settings.storage_region,
            settings.storage_bucket,
        )
        access_key_id = settings.storage_access_key_id.get_secret_value()
        secret_access_key = settings.storage_secret_access_key.get_secret_value()

        def storage_for(session_token: str | None) -> ObjectStorage:
            return S3ObjectStorage(
                endpoint=endpoint,
                region=region,
                bucket=bucket,
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                session_token=session_token,
            )

        if settings.storage_user_sessions:
            # One client per request, signed with that caller's own session.
            app.state.storage_for_session = storage_for
        else:
            storage = storage_for(None)
    app.state.storage = storage
    app.state.captures = capture_store
    if room_store is None:
        room_store = PostgresRoomStore(pool) if pool is not None else InMemoryRoomStore()
    app.state.rooms = room_store
    if account_store is None:
        account_store = PostgresAccountStore(pool) if pool is not None else InMemoryAccountStore()
    app.state.accounts = account_store
    if click_store is None:
        click_store = PostgresClickStore(pool) if pool is not None else InMemoryClickStore()
    app.state.clicks = click_store
    if pipeline is None:
        pipeline = (
            ModalLauncher(settings.pipeline_modal_app)
            if settings.pipeline_modal_app
            else RecordingLauncher()
        )
    app.state.pipeline = pipeline
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
