"""Interim hosting for the API: one Modal web endpoint that serves the ASGI app.

An approved, temporary route so real scans can reach the twin worker before
the production deployment exists. The service is unchanged and stateless:
settings come from the `sajao-api` Modal secret as SAJAO_* environment
variables, state lives in Postgres, and capture files go to the private
`captures` bucket in Supabase Storage, signed with each caller's own session.

    uv run --with 'modal[api-proxy-support]==1.6.4' modal deploy services/api/deploy/modal_app.py
"""

from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[3]

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
)

app = modal.App("sajao-api")


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("sajao-api")],
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
