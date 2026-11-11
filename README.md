# Sajao

**Scan your room. See it redone. Buy what fits.**

Sajao (Hindi for "decorate") is a mobile app for Android and iOS. A user films one room with any phone, says what she wants and what she can spend, and gets three complete designs built from real products that provably fit her space. She can drag, rotate and swap anything in a live 3D view, then buy each item through an affiliate link.

> Working name. Domain, app store and trademark availability have not been checked yet.

## Why it can win

| Others | Sajao |
| --- | --- |
| AI image generators invent furniture and quietly change the room | Every item is a real, in-stock product with real dimensions |
| Retailer apps show only their own catalog | Products from many brands, ranked for her, not for the seller |
| 3D planners make the user do the design work | Three finished designs in about 2 minutes, fully editable |
| Room scanning needs a recent iPhone Pro | Works on any phone camera; a tape measure locks the scale |

## How it works

1. **Capture.** A guided video sweep with an on-camera coach. One or two tape measurements verify the scale.
2. **Brief.** Mostly taps: what to include, budget, style swipes, household needs.
3. **Design.** A rules-based solver places catalog products under hard constraints (no collisions, clear walkways, within budget). A separate verifier re-checks every design before it is shown.
4. **Edit.** Live 3D view with drag, rotate, swap, lock and regenerate. AR view on supported phones.
5. **Buy.** Tap any item, or buy the whole room as a list.

Design principles: geometry is measured, never generated. The LLM only translates the brief and chat into structured instructions. Learning improves taste and ranking, never the fit rules.

## Status

Planning complete. Next step is phase 0: three proof spikes (scan accuracy on 20 tape-measured rooms, a 300-product catalog with 3D, and the layout solver on 10 rooms). See the [roadmap](docs/16-roadmap-risks-decisions.md).

## Documentation

Start with [the idea](docs/00-idea.md), then the [bottom line](docs/01-bottom-line.md). The full index is in [docs/README.md](docs/README.md).

| Topic | Document |
| --- | --- |
| Architecture | [System architecture](docs/05-system-architecture.md), [tech stack and cost](docs/15-tech-stack-and-cost.md) |
| Capture and accuracy | [Room capture](docs/06-room-capture.md), [accuracy and learning loop](docs/12-accuracy-and-learning-loop.md) |
| Design engine | [Design engine](docs/08-design-engine.md), [catalog and 3D assets](docs/07-catalog-and-3d-assets.md) |
| Experience | [Product flow](docs/04-product-flow-and-brief.md), [editor and AR](docs/09-editor-and-ar.md), [design language and motion](docs/10-design-language-and-motion.md) |
| Business | [Competitive landscape](docs/03-competitive-landscape.md), [commerce](docs/13-commerce.md), [extra features](docs/14-extra-features.md) |

## Planned repository layout

```
apps/mobile      React Native app (capture, brief, editor shell)
apps/editor      three.js room editor shared by app and web
services/api     FastAPI backend: rooms, catalog, designs, links
services/engine  Layout solver, verifier, ranker
services/recon   Room reconstruction workers
ml/              Training, evaluation gates, golden set tooling
docs/            Idea, solution blueprint, decisions
```

Proprietary. All rights reserved.
