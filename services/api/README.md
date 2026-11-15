# API

The Sajao API: a stateless FastAPI modular monolith behind a versioned `/v1`. Product modules (rooms, taste, designs, catalog, commerce, Vastu, admin) each add a router under `src/sajao_api/v1`.

## What is here

| Piece | File | Behavior |
| --- | --- | --- |
| Settings | `settings.py` | Read from `SAJAO_*` environment variables only. No settings file is ever loaded. A database is required outside dev. |
| Health | `v1/health.py` | `GET /v1/health`. Liveness only. |
| Request context | `middleware/request_context.py` | `X-Request-ID` on every response and one JSON log line per request. Query strings, headers and bodies are never logged. |
| Minimum app version | `middleware/app_version.py` | Apps sending an `X-App-Version` below the minimum get `426` with code `app_update_required`. |
| Idempotency | `middleware/idempotency.py`, `idempotency.py` | Every write needs an `Idempotency-Key`. See below. |
| OpenAPI | `openapi.py`, `openapi.json` | The exported document the typed client in `packages/api-client` is generated from. |

Errors always have one shape: `{"error": {"code": "...", "message": "..."}}`.

## Idempotency

| Situation | Result |
| --- | --- |
| Write without a valid `Idempotency-Key` | `400 idempotency_key_required`; the handler does not run |
| First request with a key | Runs; the response is stored |
| Retry with the same key and same request | Stored response replayed with `Idempotency-Replayed: true`; the handler does not run again |
| Same key, different method, path, query or body | `422 idempotency_key_reused` |
| Same key while the first is still running | `409 request_in_progress` |
| First attempt ended in a 5xx or crashed | Nothing stored; a retry runs again |
| Unfinished request older than the in-progress window | A retry takes it over |

Keys are stored in Postgres (`private.idempotency_keys`) so any instance can answer a retry. Without a database (dev only) they are kept in memory.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `SAJAO_ENVIRONMENT` | `dev` | `dev`, `staging` or `production` |
| `SAJAO_DATABASE_URL` | none | Postgres connection string; required outside dev |
| `SAJAO_MIN_APP_VERSION` | `0.0.0` | Oldest app version allowed |
| `SAJAO_LOG_LEVEL` | `INFO` | Log level |
| `SAJAO_IDEMPOTENCY_TTL_SECONDS` | `86400` | How long a finished write can be replayed |
| `SAJAO_IDEMPOTENCY_IN_PROGRESS_SECONDS` | `60` | How long an unfinished write blocks retries |

Secrets are set in the platform's secret manager and reach the service as environment variables. Never commit them.

## Local development

The local stack is the Supabase CLI (needs Docker). No cloud keys are involved.

```
npx supabase start                     # local Postgres and services; applies supabase/migrations
npx supabase status                    # prints the local database URL
SAJAO_DATABASE_URL=<local database URL> uv run uvicorn --factory sajao_api.main:create_app --reload
```

Database changes go only through new files in `supabase/migrations`, and must be backward compatible (expand, then contract).

## Tests and the typed client

```
uv run pytest services/api                             # in-memory store only
SAJAO_TEST_DATABASE_URL=<local database URL> uv run pytest services/api   # also runs every idempotency test on Postgres
pnpm --filter @sajao/api-client generate               # re-export OpenAPI and regenerate the client
```

CI runs the Postgres tests against a throwaway database and fails if `openapi.json` or the generated client is stale.
