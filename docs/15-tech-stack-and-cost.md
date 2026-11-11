# Tech stack and cost per design

A modular monolith with async jobs is enough until real usage says otherwise. Expected variable cost is about 1 to 3 rupees per design, since nothing generative runs in the core loop.

| Layer | Choice | Reason |
| --- | --- | --- |
| Mobile app | React Native (Expo) | One codebase for iOS and Android screens |
| Capture | Plain camera capture everywhere; optional Swift (ARKit, RoomPlan) and Kotlin (ARCore) boosters | Works on any phone; AR only adds speed |
| 3D editor | three.js, shared by app and web | One editor, shareable by link |
| 3D assets | GLB with mesh and texture compression, served from a CDN | Small downloads on mobile data |
| Backend | Python, FastAPI, modular monolith | Same language as the ML and solver code |
| Database | Postgres with pgvector (Supabase is fine to start) | Rooms, catalog, embeddings and auth in one place |
| Jobs | Queue plus workers | Scans and renders are asynchronous |
| GPU | Serverless GPU that scales to zero | Pay only for reconstruction and renders |
| Solver | Python, OR-Tools, Shapely | CPU only, deterministic, unit-testable |
| Ranking | Gradient-boosted ranker first, neural recommender later | Trains in minutes on a CPU |
| Model ops | Model registry, scheduled training, eval gate | The self-improving loop |
| LLM | Small model behind an internal gateway, prompt caching | Cheap and swappable |
| Analytics | Product analytics plus the raw event log | Events are the training data |

Estimated variable cost per design (to be measured in the first benchmark):

| Step | LiDAR or manual entry | Universal camera path (most users) |
| --- | --- | --- |
| Capture and geometry | 0 | About 0.5 to 1.5 rupees of GPU time |
| Brief parsing | About 0.5 rupees | About 0.5 rupees |
| Retrieval, solver, verifier | Under 0.1 rupees | Under 0.1 rupees |
| Storage and delivery | About 0.2 rupees | About 0.3 rupees |
| **Total** | **About 1 rupee** | **About 1.5 to 3 rupees** |

An optional photoreal render adds roughly 2 to 8 rupees each, which is why it is gated. Early fixed infrastructure should fit in 5,000 to 10,000 rupees a month.
