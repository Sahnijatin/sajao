# Sajao

**Scan your room. See it redone. Buy what fits.**

Sajao (Hindi for "decorate") is a mobile app for Android and iOS. You share a few photos or a short video of a room, tell us a little about your taste and budget, and get three exciting redesigns of your own room. Every item in them is a real, in-stock product that fits the space, with a price and a buy or rent link.

> Working name. Domain, store and trademark checks are in progress.

## The three non-negotiables

1. **Visual quality.** The redesigned room must genuinely excite you.
2. **Spatial credibility.** Dimensions and furniture make sense; every design passes a verifier.
3. **Commercial utility.** Every item is a real product with a price and a working link.

All three are rendered from one `Design` object, so the image, the plan and the shopping list can never disagree.

## How it works

1. **Understand my room.** Photos or a 10 to 30 second video. Geometry models estimate the room with an error band on every dimension; optional tape values make it Verified.
2. **Understand my taste.** Age band and household, adaptive style swipes, optional reference images, budget.
3. **Show my possibilities.** An AI designer picks real products, a solver places them, a verifier checks fit, and a guided image edit shows your own photo redesigned.
4. **Help me execute.** Shopping list with totals, buy or rent links, a dimensioned plan, Vastu guidance and a before and after reel.

AI decides taste and appearance; geometry and code decide fit; everything is checked before you see it.

## Documentation

Start with [the idea](docs/00-idea.md) and [principles and scope](docs/01-bottom-line.md). The full index is in [docs/README.md](docs/README.md). Rules every change follows are in [ENGINEERING.md](ENGINEERING.md). Sprints, tasks, decisions and scope changes are tracked in Notion.

## Repository layout

```
apps/mobile        Expo (React Native) app
apps/web           Landing page and shared-design web viewer
apps/admin         Catalog curation, support, flags and cost dashboard
services/api       Python FastAPI modular monolith (versioned /v1 API)
services/workers   Durable pipeline steps and GPU work on Modal
services/gateway   Model gateway library: fallbacks, spend caps, caching, call log
packages/schemas   Versioned JSON schemas: Capture, RoomProfile, TasteProfile, Brief, Product, Design, Render, Plan, ShoppingList, Event
packages/ui        Theme tokens, components, motion presets, haptic map
packages/api-client  Typed TypeScript client generated from the API's OpenAPI document
supabase/          Local stack config and database migrations
eval/              Golden set tooling, render bake-off, evaluation suite
docs/              Product and engineering documentation
```

## Development

TypeScript packages use pnpm workspaces; Python services use a uv workspace. The same commands run in CI as the fast tier.

```
pnpm install                    # TypeScript dependencies
pnpm check                      # lint, format check, typecheck, tests
uv sync --all-packages          # Python dependencies
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
python scripts/check_docs.py    # docs hygiene
```

Proprietary. All rights reserved.
