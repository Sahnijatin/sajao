# Tech stack and cost

A modular monolith with GPU workers that scale to zero is enough until real usage says otherwise.

| Layer | Choice | Reason |
| --- | --- | --- |
| Mobile app | React Native with Expo (dev builds) | One codebase, native modules where needed |
| Camera and guides | react-native-vision-camera with frame processors | Edge detection and sharpness checks on every phone without on-device AI |
| Motion and effects | Reanimated, Gesture Handler, Skia | 60 fps springs, glass, glows, scanning grid |
| 3D | react-native-filament | Native physically based rendering, light on budget phones |
| Haptics | expo-haptics plus native patterns | Designed haptic map |
| AR boosters | ARCore and ARKit poses; RoomPlan on LiDAR iPhones | Optional accuracy and speed |
| Backend | Python, FastAPI, modular monolith | Same language as engine and model code |
| Database | Postgres with pgvector (Supabase to start) | Rooms, catalog, embeddings, auth |
| Jobs | Queue plus workers | Scans, renders and asset generation are asynchronous |
| GPU | Serverless GPU that scales to zero | Pay only while working |
| Solver | OR-Tools, Shapely | CPU, deterministic, testable |
| Model gateway | One internal service for all model calls | Swap providers in one place, caching, caps, cost logging |
| Entitlements | In-app billing with remote switches, off at launch | Paywall can be enabled later without an app update |
| Observability | Crash reporting and product analytics from the first build | Find failures on real phones |

## Estimated variable cost per room (to be measured in phase 0)

| Step | Cost |
| --- | --- |
| Reconstruction and segmentation | 2 to 3 rupees |
| AI designer loop for three designs | 5 to 20 rupees |
| Photo render of the opened design | 3 to 6 rupees hosted; less self-hosted |
| AI judge | 1 to 3 rupees |
| Storage and delivery | Under 1 rupee |
| **Total** | **About 12 to 30 rupees** |

The launch budget is 5,000 to 20,000 rupees a month for cloud costs. To stay inside it during the free launch:

- Render photoreal only when a design is opened.
- Self-host the image model on serverless GPU if hosted costs dominate.
- Cap free rooms and regenerations per user per day.
- Budget alerts and an automatic soft limit on daily spend.
