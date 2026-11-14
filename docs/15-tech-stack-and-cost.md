# Tech stack and cost

## Stack

| Layer | Choice |
| --- | --- |
| Mobile | Expo (React Native, dev builds, EAS Build, Submit and Update), TypeScript, Expo Router |
| UI and motion | Reanimated, Gesture Handler, Skia, expo-haptics, react-native-filament (3D, Next) |
| Camera | react-native-vision-camera with frame processors for guides |
| App state | Zustand for UI state, TanStack Query for server state |
| Backend | Python FastAPI modular monolith, stateless, on Google Cloud Run in Mumbai |
| Pipeline workers | Modal: GPU geometry, model calls, renders, nightly catalog sync; durable steps with idempotency |
| Data | Supabase in Mumbai: Postgres, JSONB, pgvector, row-level security, Auth, Realtime |
| Auth | Supabase Auth: Truecaller, Google, Apple, WhatsApp OTP fallback, anonymous guest sessions |
| Media | Cloudflare R2 and image CDN; resumable uploads; signed URLs |
| Models | One model gateway: primary, fallback, caps, caching, logging per call |
| Solver | OR-Tools, Shapely |
| Subscriptions | RevenueCat (entitlements off at launch) |
| Observability | Sentry (crashes, errors), PostHog (product analytics, feature flags) |
| Web | Landing page and shared-design viewer on Vercel |
| CI | GitHub Actions; EAS Build for apps |

## Model gateway

Per-provider concurrency limits, backoff, a circuit breaker to the fallback provider, caching by content hash, parallel renders, batch pricing for offline catalog work, per-call cost and latency logging, and spend caps per user, per day and globally. The fallback chain ends in a degraded mode (3D render instead of photo render, rules instead of the AI designer), so the app never stops suddenly.

## Estimated variable cost per room

To be measured on the default path. USD at about 88 rupees.

| Step | Estimate |
| --- | --- |
| Room understanding (GPU seconds) | Rs 1 to 3 |
| Brief, designer and judge calls | Rs 3 to 6 |
| Three design renders at 1K on the cheaper image model | Rs 12 to 18 |
| Opened design upgraded to 2K on the premium model | Rs 12 |
| Storage, delivery, reel | Rs 1 to 2 |
| **Total** | **about Rs 30 to 40** |

At a cloud budget of 5,000 to 20,000 rupees a month that is roughly 150 to 650 full rooms a month, so caps, caching and per-user soft limits matter from day one. Funding is added if traffic outgrows the budget.
