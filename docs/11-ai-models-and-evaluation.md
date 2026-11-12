# AI models and evaluation

AI decides taste and appearance; code decides geometry and fit. Every model output passes a measurable check before she sees it.

## Models

| Job | Model | License | Tier |
| --- | --- | --- | --- |
| Camera positions and rough shape | MapAnything or VGGT (benchmark both) | Apache 2.0 release; commercial checkpoint | Must |
| Depth assist | Depth Anything 3 Base, Small or Metric | Apache 2.0 | Must, if it helps in phase 0 |
| Surface and item segmentation | SAM 3 | SAM license (commercial use allowed) | Must |
| Image to 3D for products | TRELLIS.2, SAM 3D Objects | MIT; SAM license | Must (offline) |
| Style and product embeddings | Open embedding model | Permissive, to confirm | Must |
| Brief parsing, product extraction, AI designer | Language models behind the model gateway | Provider terms | Must |
| Photo render harmonization | Qwen-Image-Edit-2509 or hosted Gemini image model | Apache 2.0; provider terms | Must |
| Floor plan reading, chat, AI judge | Vision and language models | Provider terms | Next |
| Taste ranker, compatibility model, catalog checker | Small models trained by us | Ours | Next |
| Layout rules, archetypes, Vastu rules | Hand-authored | Ours | Must |

Every license is recorded and re-checked before a model enters the pipeline. All model calls go through the gateway described in [tech stack and cost](15-tech-stack-and-cost.md), which handles fallbacks.

## Training data for our own models (Next tier)

- **Taste ranker:** blind pairwise votes on our own renders, the reference library, and expert review.
- **Compatibility model:** curated looks from brand lookbooks (with brand permission), designer sets, and reference reels (with creator permission).
- **Catalog checker:** products approved or rejected during curation.

Permissions for every external source are logged before use.

## Evaluation tiers

| Tier | Runs | Contents | Blocks merge? |
| --- | --- | --- | --- |
| Fast | Every commit, in CI | Schema round trips, solver and verifier property tests, relaxation order tests, fixed-room design tests, Vastu rule cases | Yes |
| Nightly | Scheduled | Reconstruction benchmark on the golden set, render outline and likeness checks, cost per room | No; regressions are reviewed |
| Release | Before each store release | Blind human votes, catalog audit, device matrix run | Yes, for the release |

Nightly and release measurements are compared with confidence intervals, not single numbers, so noise does not block work.

## Not doing

Generating whole rooms with an image model; training our own reconstruction or image model; fine-tuning a large language model before real usage data exists.

## v2: learning from users

Swaps, drags, saves, purchases and winning designs tune the taste ranker and soft scores through a gated pipeline (candidate, evaluation, shadow, small traffic share, promote or roll back). Hard rules and the verifier never change from learning.
