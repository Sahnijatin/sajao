# Sajao

**Scan your room. See it redone. Buy what fits.**

Sajao (Hindi for "decorate") is a mobile app for Android and iOS. A user scans one room, measures it with a tape in a minute or two, says what she wants and what she can spend, and gets three complete designs built from real, curated products that fit her measured space. She sees them in 3D within moments, then as her own photo redesigned, drags, rotates and swaps anything, buys each item through an affiliate link, and shares a before and after reel of her room.

> Working name. Domain, app store and trademark availability are still to be checked.

## Status

**Design intent. Phase 0 has not started.** Nothing in these docs has been tested yet. Statements about how a part works describe the intended design; claims marked **(unvalidated)** must be proven in phase 0 before anything is built on them. The v1 cut line is in [principles and scope](docs/01-bottom-line.md); gates with numbers are in the [roadmap](docs/16-roadmap-risks-decisions.md).

## Why it can win

| Others | Sajao |
| --- | --- |
| AI image generators invent furniture and quietly change the room | Every item is a real, in-stock product with real dimensions, placed in a tape-measured room |
| Retailer apps show only their own catalog | Curated products from the brands that make spaces beautiful, across retailers |
| 3D planners make the user do the design work | Three finished designs, fully editable |
| Room scanning needs a recent iPhone Pro | Works on any phone camera; the tape sets the numbers |
| Vastu apps trust a phone compass indoors | Direction is cross-checked three ways before any Vastu advice is given |

## How it works

1. **Scan.** A short guided walk around the room. The scan drafts the plan, finds doors, windows and existing furniture, and records the photos used later.
2. **Measure.** Length, width and ceiling height with a tape, entered on the drafted plan.
3. **Brief.** Mostly taps: room, budget, style swipes, Vastu preference.
4. **Design.** An AI designer proposes; a constraint solver places; an independent verifier blocks anything that does not fit.
5. **Reveal.** 3D designs first, then her own photo redesigned, with lamps on.
6. **Edit, buy, share.** Drag, swap, buy, and share an automatic before and after reel.

Geometry is measured, never generated. AI decides taste and appearance; code decides fit, and everything is checked before she sees it.

## Documentation

Start with [the idea](docs/00-idea.md), then [principles and scope](docs/01-bottom-line.md). The full index is in [docs/README.md](docs/README.md). Rules every change must follow are in [ENGINEERING.md](ENGINEERING.md).

## Planned repository layout

```
apps/mobile        Expo (React Native) app: capture, brief, reveal, editor, share
apps/web           Landing page and, later, a lightweight web viewer
services/api       Python FastAPI modular monolith: rooms, catalog, designs, links, design engine
services/gpu       GPU workers: reconstruction, segmentation, photo render, 3D asset generation
packages/schemas   Versioned JSON schemas: room, product, brief, design
eval/              Golden set tooling, benchmarks, evaluation suite
docs/              Idea, blueprint, decisions
```

Proprietary. All rights reserved.
