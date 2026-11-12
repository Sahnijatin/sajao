# AI models and evaluation

The rule: AI decides taste and appearance; code decides geometry and fit. Every model output passes a measurable check before she sees it.

## Models in v1

| Job | Model | License | Runs | Ours or pretrained |
| --- | --- | --- | --- | --- |
| Metric reconstruction | MapAnything or VGGT (benchmark both) | Apache 2.0 release; commercial checkpoint | GPU worker | Pretrained |
| Depth assist | Depth Anything 3 Base, Small or Metric | Apache 2.0 | GPU worker | Pretrained |
| Segmentation of walls, floor, items | SAM 3 | SAM license (commercial use allowed) | GPU worker | Pretrained |
| Image to 3D for products | TRELLIS.2, SAM 3D Objects | MIT; SAM license | GPU worker, offline | Pretrained |
| Style and product embeddings | Open image and text embedding model | Permissive, to confirm | GPU or CPU | Pretrained |
| Brief parsing, product extraction, floor plan reading, AI designer, chat | Language and vision models behind one internal gateway | API terms | Cloud API | Pretrained |
| Photo render | Qwen-Image-Edit-2509 or hosted Gemini image model | Apache 2.0; API terms | GPU worker or API | Pretrained |
| AI judge | Vision model with a fixed rubric | API terms | Cloud API | Pretrained, calibrated by us |
| Taste ranker | Small network on frozen image embeddings | Ours | CPU | **Trained by us** |
| Compatibility ("goes together") | Small pairwise model on product embeddings | Ours | CPU | **Trained by us** |
| Catalog checker | Small classifier | Ours | CPU | **Trained by us** |
| Layout rules, archetypes, Vastu rules | Hand-authored | Ours | CPU | **Authored by us** |

Every license is re-checked before a model enters the pipeline.

## What we train before launch, and from what

- **Taste ranker.** Learns "which room looks better" from blind pairwise votes: the reference library, an expert reviewer, and 50 to 100 people voting on pairs. A few thousand votes is enough. Trains in minutes on a CPU.
- **Compatibility model.** Learns which lamp suits which sofa and rug from curated looks: brand lookbooks, designer sets, and the "after" frames of reference reels.
- **Catalog checker.** Learns from products approved or rejected during curation.

These models only judge taste. They can make a design less attractive, never one that does not fit.

## Evaluation suite (runs on every change)

| Set | Measures | Scored by |
| --- | --- | --- |
| Golden rooms: tape-measured, scanned on every phone tier | Wall, door and window error after the tape check; orientation error | Automatic |
| Layout set: 100+ real rooms | Hard-rule pass rate, archetype coverage, quality | Automatic, plus a designer rubric on a sample |
| Taste test | Preference for our design versus a reference | Blind pairwise human votes |
| Render fidelity | Product likeness in photo renders | Embedding similarity, plus human spot checks |
| Catalog audit | Dimension accuracy | Random 5% checked against brand pages |
| Vastu cases | Rules fire correctly | Expert-approved test rooms |
| AI judge calibration | Agreement between the judge and human votes | Measured; the judge is trusted only as far as it agrees |

A change that makes any slice worse does not ship. Slices: room type, room size, lighting, phone tier, city.

## What we are deliberately not doing

- Generating the whole room with an image model: that is how competitors invent furniture and change rooms.
- Training our own reconstruction or image model: pretrained open models are already better than what we could train.
- Fine-tuning a large language model before there is real usage data.

## v2: learning from users

Swaps, drags, saves, purchases and which design won tune the taste ranker and soft scores, through a gated pipeline: train a candidate, score it on the evaluation suite and replayed history, run it in shadow, then on a small share of traffic, promote or roll back. Scans from LiDAR iPhones paired with camera-only results tune the universal capture path. Hard rules and the verifier never change from learning.
