# Tech stack and cost

| Layer | Choice | Reason |
| --- | --- | --- |
| Mobile app | React Native with Expo (dev builds) | One codebase, native modules where needed |
| Camera and guides | react-native-vision-camera with frame processors | Edge and sharpness checks on every phone without on-device AI |
| Motion and effects | Reanimated, Gesture Handler, Skia | 60 fps springs, glass, glows, scanning grid |
| 3D | react-native-filament | Native rendering, light on budget phones |
| Haptics | expo-haptics plus native patterns | Designed haptic map |
| Backend | Python, FastAPI, modular monolith | Same language as engine and model code |
| Database | Postgres with pgvector (Supabase to start) | Rooms, catalog, embeddings, auth |
| Jobs | Queue plus workers | Scans, renders and asset generation are asynchronous |
| GPU | Serverless GPU with memory snapshots | Pay only while working; faster cold starts |
| Solver | OR-Tools, Shapely | CPU, deterministic, testable |
| Model gateway | One internal service for all model calls | Fallbacks, caching, caps, cost logging, provider swap |
| Observability | Crash reporting and product analytics from the first build | Find failures on real phones |

## Model gateway and the fallback chain

The app never stops suddenly. Each model job has an ordered chain; the gateway moves down it on errors, timeouts or when a cost cap is reached:

| Step | Language and vision jobs | Image render jobs |
| --- | --- | --- |
| 1. Primary | Best-quality hosted model | Primary image model |
| 2. Open-model aggregator | Open-weight models through a pay-per-use aggregator (for example NanoGPT or similar) | Self-hosted Qwen-Image-Edit on serverless GPU |
| 3. Self-hosted open model | Small open model on our own GPU worker | Same, queued |
| 4. Degraded mode | Templates plus rules, no AI designer | 3D render instead of photo render; photo render queued and delivered later with a notification |

Notes:

- Aggregator terms must allow serving end users in a production app. NanoGPT's subscription was reported at 12 dollars a month from May 2026 with a weekly token cap and open-weight models only; confirm terms before relying on it.
- NVIDIA's free API catalog is for evaluation and prototyping; production use needs paid endpoints. Usable for phase 0 experiments, not as a launch fallback.
- The gateway logs provider, model, latency and cost for every call.

## Latency

No fixed time is promised. Results are staged (3D first, photo render after). GPU workers stay warm during peak evening hours, use memory snapshots otherwise, and every step's latency is measured nightly.

## Estimated variable cost per room (to be measured in phase 0)

| Step | Default path | With optional critique and extra renders |
| --- | --- | --- |
| Reconstruction and segmentation | 2 to 3 rupees | 2 to 3 rupees |
| AI designer | 2 to 6 rupees (single pass) | 5 to 20 rupees |
| Photo render of the opened design | 3 to 6 rupees hosted; less self-hosted | Per extra render |
| Storage and delivery | Under 1 rupee | Under 1 rupee |
| **Total** | **About 8 to 15 rupees** | **About 12 to 30 rupees** |

Launch cloud budget: 5,000 to 20,000 rupees a month, with invites, per-user daily caps, spend alerts, and the fallback chain. If demand exceeds it, funding is added rather than turning users away.
