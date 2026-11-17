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
    )
    .add_local_dir(ROOT / "services/api/src/sajao_api", "/root/sajao_api")
    .add_local_dir(ROOT / "packages/schemas/python/sajao_schemas", "/root/sajao_schemas")
    # The pipeline's stages; the ones run here are plain Python on a CPU.
    .add_local_dir(ROOT / "services/workers/src/sajao_workers", "/root/sajao_workers")
)

# Step results, content addressed: a room that is run again reuses them.
artifacts = modal.Volume.from_name("sajao-pipeline", create_if_missing=True)
ARTIFACTS = "/artifacts"

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
    secrets=[modal.Secret.from_name("sajao-api"), modal.Secret.from_name("sajao-pipeline")],
    volumes={ARTIFACTS: artifacts},
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

    artifacts.reload()  # a warm container sees what other runs stored
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
        capture = await rooms.capture_for_room(room_id)
        if capture is None:
            return "unknown room"
        runner = StepRunner(LocalArtifactStore(Path(ARTIFACTS)))
        run = await pipeline.run_room(runner, rooms, _CaptureFiles(), room_id, capture)
        return run.outcome
    finally:
        await pool.close()
        artifacts.commit()


@app.function(image=image, timeout=60)
async def run_designs(room_id: str, request_id: str) -> str:
    """Design stages are not handed over yet: the request stays queued."""
    return "queued"
