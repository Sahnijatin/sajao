"""Interim hosting for the API: one Modal web endpoint that serves the ASGI app.

An approved, temporary route so real scans can reach the twin worker before
the production deployment exists. The service is unchanged and stateless:
settings come from the `sajao-api` Modal secret as SAJAO_* environment
variables, state lives in Postgres, and capture files go to the private
`captures` bucket in Supabase Storage, signed with each caller's own session.

The durable pipeline runs beside it as `run_room` and `run_designs`: the API
spawns them by name and returns at once. Only `run_room` mounts the
`sajao-pipeline` secret, which lets it read any user's capture files.

    uv run --with 'modal[api-proxy-support]==1.6.4' modal deploy services/api/deploy/modal_app.py
"""

from pathlib import Path
from typing import Any

import modal

HERE = Path(__file__).resolve()
# Inside the container this file sits alone in /root: the repository root only
# exists where the deployment is run from, which is where the image is built.
ROOT = HERE.parents[3] if len(HERE.parents) > 3 else HERE.parent

image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install(
        "fastapi==0.163.0",
        "boto3==1.44.3",
        "psycopg[binary,pool]==3.3.9",
        "pyjwt[crypto]==2.15.1",
        "pydantic-settings==2.16.3",
        "structlog==26.1.0",
        "pydantic==2.14.3",
        # The photo stages: geometry in numpy, photos in Pillow, the item-list models.
        "numpy==2.5.5",
        "pillow==13.0.0",
        "anthropic==2.8.0",
        "google-auth[requests]==2.62.2",
        "httpx==0.28.1",
    )
    .add_local_dir(ROOT / "services/api/src/sajao_api", "/root/sajao_api")
    .add_local_dir(ROOT / "packages/schemas/python/sajao_schemas", "/root/sajao_schemas")
    # The pipeline's stages; the ones run here are plain Python on a CPU.
    .add_local_dir(ROOT / "services/workers/src/sajao_workers", "/root/sajao_workers")
    .add_local_dir(ROOT / "services/gateway/src/sajao_gateway", "/root/sajao_gateway")
    # The design engine and the catalog code (the gate's sizing, the visibility rule).
    .add_local_dir(ROOT / "services/engine/src/sajao_engine", "/root/sajao_engine")
    .add_local_dir(ROOT / "services/catalog/src/sajao_catalog", "/root/sajao_catalog")
)
# Products a design may use (development catalog until feeds are approved).
CATALOG_FILE = ROOT / "services/catalog/data/development/catalog.jsonl"

# Step results, content addressed, in one folder per user: a room that is run
# again reuses them, and erasing an account removes its folder.
artifacts = modal.Volume.from_name("sajao-pipeline", create_if_missing=True)
ARTIFACTS = "/artifacts"
# The GPU worker's volume (app sajao-twin-worker): a photo room's blobs are copied
# there for a model call and back, and the copies deleted (sajao_workers.gpu_bridge).
gpu_volume = modal.Volume.from_name("sajao-twin", create_if_missing=True)
GPU_STORE = "/gpu"
GPU_APP = "sajao-twin-worker"

app = modal.App("sajao-api")


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("sajao-api"),
        # Not a secret: which Modal app runs the pipeline (this one).
        modal.Secret.from_dict({"SAJAO_PIPELINE_MODAL_APP": "sajao-api"}),
    ],
    # Scales to zero between scans; a few containers are plenty for testing.
    min_containers=0,
    max_containers=3,
    scaledown_window=300,
    timeout=120,
)
@modal.concurrent(max_inputs=50)
@modal.asgi_app()
def api() -> object:
    from sajao_api.main import create_app

    return create_app()


class _CaptureFiles:
    """Reads any user's capture files: the one place that holds that right.

    `SAJAO_PIPELINE_STORAGE_TOKEN` (Modal secret `sajao-pipeline`) is a storage
    session that passes row level security; the API itself never has it.
    """

    def __init__(self) -> None:
        import os

        import boto3

        self._bucket = os.environ["SAJAO_STORAGE_BUCKET"]
        self._client = boto3.client(
            "s3",
            endpoint_url=os.environ["SAJAO_STORAGE_ENDPOINT"],
            region_name=os.environ["SAJAO_STORAGE_REGION"],
            aws_access_key_id=os.environ["SAJAO_STORAGE_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["SAJAO_STORAGE_SECRET_ACCESS_KEY"],
            aws_session_token=os.environ["SAJAO_PIPELINE_STORAGE_TOKEN"],
        )

    def read(self, storage_key: str) -> bytes:
        body: bytes = self._client.get_object(Bucket=self._bucket, Key=storage_key)["Body"].read()
        return body


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("sajao-api"),
        modal.Secret.from_name("sajao-pipeline"),
        # The photo stages' item lists: Gemini on Vertex AI and Claude.
        modal.Secret.from_name("gcp"),
        modal.Secret.from_name("anthropic-secret"),
    ],
    volumes={ARTIFACTS: artifacts, GPU_STORE: gpu_volume},
    max_containers=3,
    timeout=900,
    # The step layer retries inside a stage; a crashed container is started once more.
    retries=1,
)
async def run_room(room_id: str) -> str:
    """Run a room's stages from its capture. Safe to call again at any point."""
    import os

    from psycopg_pool import AsyncConnectionPool

    from sajao_api.rooms import PostgresRoomStore
    from sajao_workers import pipeline
    from sajao_workers.steps import LocalArtifactStore, StepRunner

    await artifacts.reload.aio()  # a warm container sees what other runs stored
    pool = AsyncConnectionPool(
        os.environ["SAJAO_DATABASE_URL"],
        open=False,
        min_size=1,
        max_size=2,
        kwargs={"prepare_threshold": None, "autocommit": True},
    )
    await pool.open()
    try:
        rooms = PostgresRoomStore(pool)
        found = await rooms.capture_for_room(room_id)
        if found is None:
            return "unknown room"
        user_id, capture = found
        store = LocalArtifactStore(Path(ARTIFACTS) / user_id)
        runner = StepRunner(store)
        one, few = _photo_stages(store) if pipeline.photo_count(capture) else ((), ())
        run = await pipeline.run_room(
            runner, rooms, _CaptureFiles(), room_id, capture, photo_stages=one, few_photo_stages=few
        )
        if run.outcome == "done":
            # Design requests the app sent while the room was being read start now.
            for request_id in await rooms.pending_design_requests(room_id):
                await run_designs.spawn.aio(room_id, request_id)
        return run.outcome
    finally:
        await pool.close()
        await artifacts.commit.aio()


def _photo_stages(store: Any) -> tuple[Any, Any]:
    """The photo-first stages (one photo, and two or three), their GPU calls bridged to
    the worker's volume."""
    from sajao_workers.gpu_bridge import bridged
    from sajao_workers.photo_pipeline import (
        few_photo_stages,
        photo_models,
        photo_room_stages,
        room_ledger,
    )
    from sajao_workers.steps import LocalArtifactStore

    run_model = modal.Function.from_name(GPU_APP, "run_model")
    run_splat = modal.Function.from_name(GPU_APP, "run_splat")
    shared = LocalArtifactStore(Path(GPU_STORE) / "artifacts")

    def on(function: Any, task: str) -> Any:
        async def call(model: str, payload: Any) -> Any:
            return await function.remote.aio(model, task, dict(payload))

        return bridged(call, store, shared, gpu_volume.commit.aio, gpu_volume.reload.aio)

    models = photo_models(
        lambda task: on(run_model, task), room_ledger(), poses_gpu=on(run_splat, "twin_poses")
    )
    return photo_room_stages(models), few_photo_stages(models)


@app.function(
    image=image.add_local_file(CATALOG_FILE, "/root/catalog.jsonl"),
    secrets=[
        modal.Secret.from_name("sajao-api"),
        # This interim host serves development and closed-test builds, which may show
        # development products (SJ-DEC-84). The store release never runs here.
        modal.Secret.from_dict({"SAJAO_SHOW_FLAGGED_PRODUCTS": "1"}),
    ],
    max_containers=3,
    timeout=300,
    retries=1,
)
async def run_designs(room_id: str, request_id: str) -> str:
    """Three designs for a design request: spec and placement. The render is its own stage."""
    import datetime
    import os

    from psycopg_pool import AsyncConnectionPool

    from sajao_api.rooms import PostgresRoomStore
    from sajao_workers.design_pipeline import catalog_products, run_design_request

    pool = AsyncConnectionPool(
        os.environ["SAJAO_DATABASE_URL"],
        open=False,
        min_size=1,
        max_size=2,
        kwargs={"prepare_threshold": None, "autocommit": True},
    )
    await pool.open()
    try:
        rooms = PostgresRoomStore(pool)
        found = await rooms.design_request_for_pipeline(request_id)
        if found is None:
            return "unknown request"
        request, twin = found
        allow = os.environ.get("SAJAO_SHOW_FLAGGED_PRODUCTS", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        products = catalog_products(Path("/root/catalog.jsonl"), allow_flagged=allow)
        outcome = await run_design_request(
            rooms,
            request.room_id,
            request.request_id,
            request.brief,
            twin,
            products,
            datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        )
        return outcome.outcome
    finally:
        await pool.close()


class _UserFiles:
    """Deletes every file in one user's folder of the captures bucket."""

    def __init__(self) -> None:
        self._files = _CaptureFiles()

    def erase(self, user_id: str) -> int:
        import shutil

        # What the pipeline derived from the user's scans, then the scans.
        artifacts.reload()
        shutil.rmtree(Path(ARTIFACTS) / user_id, ignore_errors=True)
        artifacts.commit()
        client, bucket = self._files._client, self._files._bucket
        deleted = 0
        while True:
            # Listed again from the start each time: what was deleted is gone.
            page = client.list_objects_v2(Bucket=bucket, Prefix=f"{user_id}/", MaxKeys=500)
            keys = [item["Key"] for item in page.get("Contents", [])]
            if not keys:
                return deleted
            # One by one: this store refuses the batch delete call.
            for key in keys:
                client.delete_object(Bucket=bucket, Key=key)
            deleted += len(keys)


class _SignIn:
    """Deletes the user's sign-in account through the auth service's admin API."""

    async def erase(self, user_id: str) -> None:
        import asyncio
        import os
        import urllib.error
        import urllib.request

        key = os.environ["SAJAO_PIPELINE_STORAGE_TOKEN"]
        request = urllib.request.Request(  # noqa: S310
            f"{os.environ['SAJAO_AUTH_ISSUER'].rstrip('/')}/admin/users/{user_id}",
            method="DELETE",
            headers={"Authorization": f"Bearer {key}", "apikey": key},
        )

        def send() -> None:
            try:
                urllib.request.urlopen(request, timeout=30).close()  # noqa: S310
            except urllib.error.HTTPError as error:
                if error.code != 404:  # already gone is fine
                    raise

        await asyncio.to_thread(send)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("sajao-api"), modal.Secret.from_name("sajao-pipeline")],
    volumes={ARTIFACTS: artifacts},
    max_containers=2,
    timeout=900,
    retries=2,
)
async def delete_account(user_id: str) -> int:
    """Erase one user's files, rows and sign-in account. Safe to call again."""
    import os

    from psycopg_pool import AsyncConnectionPool

    from sajao_api.accounts import PostgresAccountStore, erase_account

    pool = AsyncConnectionPool(
        os.environ["SAJAO_DATABASE_URL"],
        open=False,
        min_size=1,
        max_size=2,
        kwargs={"prepare_threshold": None, "autocommit": True},
    )
    await pool.open()
    try:
        accounts = PostgresAccountStore(pool)
        if await accounts.deletion_finished(user_id) is None:
            return 0  # nobody asked: never erase on a bare call
        return await erase_account(user_id, accounts, _UserFiles(), _SignIn())
    finally:
        await pool.close()


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("sajao-api")],
    schedule=modal.Period(minutes=2),
    timeout=60,
)
async def sweep_rooms() -> int:
    """Start lost room and design jobs again; fail stuck ones with timed_out (sweep.py)."""
    import datetime
    import os

    from psycopg_pool import AsyncConnectionPool

    from sajao_api.rooms import PostgresRoomStore
    from sajao_api.sweep import sweep

    class _Spawn:
        async def start_room(self, room_id: str) -> None:
            await run_room.spawn.aio(room_id)

        async def start_designs(self, room_id: str, request_id: str) -> None:
            await run_designs.spawn.aio(room_id, request_id)

    pool = AsyncConnectionPool(
        os.environ["SAJAO_DATABASE_URL"],
        open=False,
        min_size=1,
        max_size=1,
        kwargs={"prepare_threshold": None, "autocommit": True},
    )
    await pool.open()
    try:
        done = await sweep(PostgresRoomStore(pool), _Spawn(), datetime.datetime.now(datetime.UTC))
    finally:
        await pool.close()
    for decision in done:
        print(f"sweep: {decision.action} room {decision.room_id} request {decision.request_id}")
    return len(done)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("sajao-api")],
    schedule=modal.Period(hours=1),
    timeout=120,
)
async def sweep_account_deletions() -> int:
    """Start again any erasure that was asked for and did not finish."""
    import os

    from psycopg_pool import AsyncConnectionPool

    from sajao_api.accounts import PostgresAccountStore

    pool = AsyncConnectionPool(
        os.environ["SAJAO_DATABASE_URL"],
        open=False,
        min_size=1,
        max_size=1,
        kwargs={"prepare_threshold": None, "autocommit": True},
    )
    await pool.open()
    try:
        waiting = await PostgresAccountStore(pool).unfinished_deletions()
    finally:
        await pool.close()
    for user_id in waiting:
        await delete_account.spawn.aio(user_id)
    return len(waiting)
