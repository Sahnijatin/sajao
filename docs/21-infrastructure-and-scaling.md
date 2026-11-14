# Infrastructure and scaling

Going from 10 users to 1 lakh is a configuration change, not a rewrite: stateless services, a durable job pipeline, standard Postgres, S3-compatible storage and one model gateway. At 10 users it costs close to nothing because every compute layer scales to zero.

## Load model at 1 lakh users

Assume 10,000 rooms on a busy day: about one room per second at evening peak, a few database writes per room, 3 to 5 slow model calls per room. Postgres is never the bottleneck; provider rate limits and spend are. Scaling means cost control first, capacity second.

## Decisions

1. **Database.** Supabase Postgres in Mumbai for everything relational, JSONB for Room and Design objects, pgvector for taste and product search, row-level security on user data. No separate vector or document database.
2. **Media.** Cloudflare R2 plus image CDN; renders are viewed and shared many times and R2 has no egress fees.
3. **Compute.** Stateless FastAPI on Cloud Run in Mumbai; pipeline and GPU work on Modal workers.
4. **Durable pipeline.** Each room is a job of steps; each step stores its result, retries safely with an idempotency key, and resumes where it stopped. A failed render retries only the render and never charges twice.
5. **Abuse and cost protection.** Play Integrity and App Attest on expensive endpoints, per-user and per-device limits, gateway spend caps. When a cap is hit the room waits in a queue with an honest message instead of failing.
6. **Mobile networks.** Compression on the phone, resumable background uploads, realtime status with polling fallback, push when renders finish, idempotency keys on every write.
7. **Model gateway.** Per-provider concurrency limits, backoff, circuit breaker to the fallback provider, caching by content hash, parallel renders, batch pricing for offline catalog work.

## Scale triggers

Decided with data, not upfront.

| Signal | Action |
| --- | --- |
| Database CPU above 60% at peak | Read replica, query review |
| Event table above about 50 million rows | Move analytics to a columnar warehouse |
| Catalog API latency above 300 ms p95 | CDN caching of catalog responses |
| One module dominating deploys or load | Split that module into its own service |
| Monthly spend above budget | Cheaper render tier for previews, tighter caps, funding |

Before launch the API and pipeline are load-tested at 10 times the expected launch traffic.

## Exit options

Standard Postgres, S3-compatible storage and the gateway keep us free to change any vendor.
