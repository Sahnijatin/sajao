# Model gateway

The one library every model call goes through. The API and the workers never call a provider directly.

```python
gateway = ModelGateway([primary, fallback], ledger=ledger)
response = await gateway.call(request, validate=check_spec, degraded=rules_spec)
```

## What a call does

1. **Cache.** The same content (task, prompt version, payload, images, pinned models) is answered from the cache at no cost. The user is not part of the key.
2. **Circuit breaker.** A provider that keeps failing is skipped, then probed with one trial call after a cooldown.
3. **Spend caps.** The estimated cost is reserved against the per-user daily cap and the global daily cap before the call, and settled to the real cost after it. A cheaper fallback is tried when the primary would pass a cap.
4. **Limits and retries.** Per-provider concurrency limit, a timeout, and retries with exponential backoff and jitter. A provider may declare its own `timeout_seconds` (a GPU job that runs for minutes) and `max_attempts` (an expensive job its durable step retries instead). Errors marked not retryable move straight to the next provider.
5. **Validation.** `validate` is required. An output that fails it is treated as a failure and is never returned or cached.
6. **Call log.** Every attempt is recorded with provider, pinned model, outcome, latency and cost. Prompts, payloads and outputs are never logged; only the content hash is.
7. **Degraded mode.** When every provider fails, the optional `degraded` step answers (rules instead of a model, a 3D render instead of a photo render), marked `degraded=True`, so the app never stops suddenly.

## What the caller handles

| Raised | Meaning | What to do |
| --- | --- | --- |
| `SpendCapExceededError` | Nothing ran, only because of a cap (`scope` is `user` or `global`) | Queue the work and show an honest message |
| `AllProvidersFailedError` | Every provider failed and no degraded step was given | Fail the step; the durable pipeline retries it |

## Adding a provider

Implement the `Provider` protocol: a unique `name`, a pinned `model`, the `modalities` it supports, `max_concurrency`, `estimate_cost_micro_inr` (an upper bound) and `call`. Raise `ProviderError(retryable=False)` for requests that can never succeed. Record the model's license before it enters a chain.

Costs are whole micro-rupees (1 rupee = 1,000,000).

## Not here yet

- **More real providers.** `ClaudeProvider` (`sajao_gateway.claude`, text and vision through the Anthropic API) is the first; it reads `ANTHROPIC_API_KEY` from the environment and computes each call's cost from token usage. `daily_cap_micro_inr()` sizes a global daily cap to a monthly budget. Image models are still wired per job.
- **Shared state.** The ledger, cache and breaker are in-memory, which suits tests and a single worker. Running services need ledger and cache implementations backed by the database, behind the same `SpendLedger` and `ResponseCache` protocols.
- **Per-device caps and batch pricing** for offline catalog work.
