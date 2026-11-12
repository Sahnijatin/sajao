# Sajao

**Scan your room. See it redone. Buy what fits.**

Sajao (Hindi for "decorate") is a mobile app for Android and iOS. A user sweeps her phone around one room, says what she wants and what she can spend, and gets three complete designs built from real, curated products that provably fit her space. She sees them first as her own photo, redesigned, then drags, rotates and swaps anything in a live 3D view, buys each item through an affiliate link, and shares a before and after reel of her room.

> Working name. Domain, app store and trademark availability are still to be checked.

## Why it can win

| Others | Sajao |
| --- | --- |
| AI image generators invent furniture and quietly change the room | Every item is a real, in-stock product with real dimensions, placed by measured geometry |
| Retailer apps show only their own catalog | Curated products from the brands that make spaces beautiful, across retailers |
| 3D planners make the user do the design work | Three finished designs, fully editable, in about two minutes |
| Room scanning needs a recent iPhone Pro | Works on any phone camera; one tape measurement locks the scale |
| Vastu apps trust a phone compass indoors | Direction is cross-checked three ways before any Vastu advice is given |

## How it works

1. **Scan.** A 30-second guided sweep with live alignment guides and a scanning grid. One tape measurement verifies the scale.
2. **Brief.** Mostly taps: room, budget, style swipes, Vastu preference, household.
3. **Design.** An AI designer proposes; a constraint solver places; an independent verifier blocks anything that does not fit.
4. **Reveal.** Her own photo, redesigned, with lamps on. Three designs to swipe.
5. **Edit.** Live 3D: drag, rotate, swap, lock, regenerate, day and night.
6. **Buy and share.** Tap any item to buy. Share an automatic before and after reel.

Geometry is measured, never generated. AI decides taste and appearance; code decides fit, and everything is checked before she sees it.

## Status

Planning complete. Next step is phase 0: proof spikes for capture accuracy on a golden set of measured rooms, catalog v0, and the design engine on real rooms. See the [roadmap](docs/16-roadmap-risks-decisions.md) and [engineering process](docs/17-engineering-process.md).

## Documentation

Start with [the idea](docs/00-idea.md), then [the principles](docs/01-bottom-line.md). The full index is in [docs/README.md](docs/README.md). Rules every change must follow are in [ENGINEERING.md](ENGINEERING.md).

## Planned repository layout

```
apps/mobile        Expo (React Native) app: capture, brief, reveal, editor, share
apps/web           Landing page and lightweight web viewer for shared designs
services/api       Python FastAPI modular monolith: rooms, catalog, designs, links, design engine
services/gpu       GPU workers: reconstruction, segmentation, photo render, 3D asset generation
packages/schemas   Versioned JSON schemas: room, product, brief, design
eval/              Golden set tooling, benchmarks, evaluation suite
docs/              Idea, blueprint, decisions
```

Proprietary. All rights reserved.
