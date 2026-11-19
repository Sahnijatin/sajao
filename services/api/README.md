# API

The Sajao API: a stateless FastAPI modular monolith behind a versioned `/v1`. Product modules (rooms, taste, designs, catalog, commerce, Vastu, admin) each add a router under `src/sajao_api/v1`.

## What is here

| Piece | File | Behavior |
| --- | --- | --- |
| Settings | `settings.py` | Read from `SAJAO_*` environment variables only. No settings file is ever loaded. A database is required outside dev. |
| Health | `v1/health.py` | `GET /v1/health`. Liveness only. |
| Request context | `middleware/request_context.py` | `X-Request-ID` on every response and one JSON log line per request. Query strings, headers and bodies are never logged. |
| Minimum app version | `middleware/app_version.py` | Apps sending an `X-App-Version` below the minimum get `426` with code `app_update_required`. |
| Auth | `auth.py`, `middleware/auth.py`, `v1/me.py` | Bearer tokens from the auth service are verified against its public keys. No token means anonymous; a bad token is always `401`. Endpoints that need a caller use the `current_user` dependency. Guests have a real user id. |
| Uploads | `storage.py`, `v1/uploads.py` | Resumable multipart uploads of capture media (photos, video, and the capture package's data files: sensor log, planes, depth, scene mesh) straight to object storage through short-lived signed URLs. See below. |
| Captures | `captures.py`, `v1/captures.py` | `POST /v1/captures` registers a finished scan whose files are already uploaded: the body is validated as a `Capture`, every storage key must belong to the caller, and the row is stored for the twin worker. The capture id comes from the phone, so repeating the call returns the stored capture (`200` instead of `201`). `GET /v1/captures/{id}` returns the caller's own capture. |
| Rooms and designs | `rooms.py`, `room_status.py`, `pipeline.py`, `v1/captures.py`, `v1/rooms.py` | Registering a capture (`POST /v1/captures`) is the upload's completion: it makes the capture's room (one per capture) and starts the durable pipeline, with no further call. A photo below 1024 by 576 px is refused there (`422 photo_too_small`): the render never enlarges a photo. `POST /v1/rooms` returns that room (`200`) and starts it again only if it failed: a second run of a room that is running would repeat its GPU work, and a lost start is the sweeper's to pick up. Asking again for a design request likewise starts it only if it failed. `GET /v1/rooms` and `GET /v1/rooms/{id}` return a `RoomStatus` (packages/schemas): one stage (`uploaded`, `reading`, `designing`, `rendering`, `ready`, `failed`), a `failure` with a reason from the contract's list when it failed (a code the list does not know is `internal`), the twin's `confidence_level`, and per design item whether a fit check ran; the pipeline rows stay alongside. `GET /v1/rooms/{id}/twin` returns the SpaceTwin once it exists (`409 room_not_ready` before). `POST /v1/rooms/{id}/designs` takes a request id from the phone and a `Brief` at any point: asked before the room is read, it starts when reading ends. `GET /v1/rooms/{id}/designs` returns the latest request's status and, once ready, its three Designs. The API only creates rows and reads them: the pipeline worker moves the stages and stores each result. |
| Pipeline worker | `deploy/modal_app.py`, `services/workers/src/sajao_workers/pipeline.py` | `run_room` reads the room's capture, runs its stages in order over the durable step layer and moves the stage rows. A stage that is done is never run again (its result is stored under a content hash on the `sajao-pipeline` volume), a step that fails is tried again (three tries with backoff, and a crashed container once more) and then stores a reason code (`no_walls`, `upload_incomplete`, `photo_too_small`, `floor_not_visible` and the rest of the contract's list), and a stage running elsewhere is left alone. When the room is read, `run_room` starts the design requests that were waiting. `sweep_rooms` runs every 2 minutes: it starts again a job whose start was lost and fails a stage stuck past its worker's limit with `timed_out`, so no job waits silently. Today the only stage with a step is `measure`: walls, floor, ceiling height and openings from the planes the phone tracked, computed in code. |
| Account deletion | `accounts.py`, `v1/me.py`, `deploy/modal_app.py` | `DELETE /v1/me` records the request and starts the erasure at once (`202`, status `deleting`, then `deleted`). The `delete_account` job erases what the pipeline derived from the user's scans (their folder on the `sajao-pipeline` volume) and their files in the captures bucket, then their rooms, captures and idempotency keys, then their sign-in account, and marks the request finished. Every step is safe to repeat; a sweep runs hourly and starts again any erasure that did not finish. There is no undo. An access token issued before the erasure still verifies until it expires (up to an hour). |
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

Keys belong to the caller, so two users with the same key never see each other's responses. They are stored in Postgres (`private.idempotency_keys`) so any instance can answer a retry. Without a database (dev only) they are kept in memory.

## Uploads

The file never passes through the API. The phone resizes photos to about 1600 px, then:

1. `POST /v1/uploads` with the kind, content type and size. The answer is a plan: a key, an upload id, the part size (5 MiB) and a signed URL per part.
2. `PUT` each part to its URL and keep the `ETag` from each response.
3. After a dropped connection, `POST /v1/uploads/resume`: it lists the parts that arrived and gives fresh URLs for the rest.
4. `POST /v1/uploads/complete` with the parts joins them into the stored file.

Rules: callers must be signed in or guests; keys live under the caller's user id and other users get `404`; photos up to 20 MiB and video up to 200 MiB, checked again on what really arrived; signed URLs last 15 minutes; reading stored media also needs a signed URL.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `SAJAO_ENVIRONMENT` | `dev` | `dev`, `staging` or `production` |
| `SAJAO_DATABASE_URL` | none | Postgres connection string; required outside dev |
| `SAJAO_AUTH_JWKS_URL` | none | Where the auth service publishes its public signing keys; required outside dev |
| `SAJAO_AUTH_ISSUER` | none | The issuer its tokens carry; set together with the keys URL |
| `SAJAO_STORAGE_ENDPOINT`, `_REGION`, `_BUCKET`, `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY` | none | S3-compatible object storage; set all five or none. Without them uploads answer `503` |
| `SAJAO_PIPELINE_MODAL_APP` | none | The Modal app whose `run_room` and `run_designs` functions run the pipeline. Without it nothing is started (dev and tests) |
| `SAJAO_MIN_APP_VERSION` | `0.0.0` | Oldest app version allowed |
| `SAJAO_LOG_LEVEL` | `INFO` | Log level |
| `SAJAO_IDEMPOTENCY_TTL_SECONDS` | `86400` | How long a finished write can be replayed |
| `SAJAO_IDEMPOTENCY_IN_PROGRESS_SECONDS` | `60` | How long an unfinished write blocks retries |

Secrets are set in the platform's secret manager and reach the service as environment variables. Never commit them.

## Interim hosting

Until the production deployment exists, the API runs as one Modal web endpoint (`deploy/modal_app.py`) that serves the same ASGI app, with settings from the `sajao-api` Modal secret. This is an approved, temporary route so real scans can reach the twin worker; Cloud Run in Mumbai stays the production target.

Capture files go to the private `captures` bucket in Supabase Storage on the development project (`supabase/migrations/*_captures_bucket.sql`). With `SAJAO_STORAGE_USER_SESSIONS=true` the API signs every storage request, signed part URLs included, with the caller's own access token as the session token: the access key id is the project ref and the secret is the project's public anon key. The bucket's row level security keeps each user inside the folder named after their user id, so the API holds no storage credential that could read another user's files. `SAJAO_STORAGE_MAX_OBJECT_BYTES` carries the store's own limit for one file (50 MiB there); a larger file is refused before any part is sent, and the app then leaves the scan video out and uploads the rest.

Known limits of the interim store: listing the parts of an unfinished upload returns none under a user session, so an interrupted file restarts from its first part (finished files are still skipped); and the worker needs its own server-side access to read the bucket.

```bash
uv run --with 'modal[api-proxy-support]==1.6.4' modal deploy services/api/deploy/modal_app.py
```

## Development environment

The development Supabase project is `sajao-dev` (see `supabase/README.md`). To point the API at it, set `SAJAO_AUTH_JWKS_URL` and `SAJAO_AUTH_ISSUER` to that project's values and `SAJAO_DATABASE_URL` to its connection string from the secret manager. The idempotency table is already applied there.

## Local development

The local stack is the Supabase CLI (needs Docker). No cloud keys are involved.

```
npx supabase start                     # local Postgres and services; applies supabase/migrations
npx supabase seed buckets              # creates the private captures bucket
npx supabase status                    # prints the local database URL and storage keys
# For auth, also set SAJAO_AUTH_JWKS_URL=<API URL>/auth/v1/.well-known/jwks.json and SAJAO_AUTH_ISSUER=<API URL>/auth/v1
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
