# Schemas

The contract between the app, the API and the workers. One JSON Schema source per journey object in `schemas/v1`; TypeScript types and Pydantic models are generated from it, so the three sides cannot drift.

| Object | Stage |
| --- | --- |
| `Capture` | Input |
| `SpaceProfile` | Understanding (a view of the `SpaceTwin`) |
| `SpaceTwin` | The 3D twin: shell and every object as its own item |
| `TasteProfile`, `Brief` | Personalisation |
| `Product` | Catalog item, embedded in a design |
| `Design` | Design |
| `Render`, `Plan`, `ShoppingList` | Views derived from one `Design` |
| `Event` | Action log |
| `RoomStatus` | Job status: what the room status endpoint returns |

## Rules the schemas enforce

- Every dimension is a `Dimension`: a value in metres, a source (`measured`, `estimated`, `user_confirmed`) and an error band. A test fails if a bare length is added anywhere else.
- A space is whatever was scanned: `Capture` has no room type. `SpaceProfile` carries the detected `space_type` and `extent`, who set each (`detected` or `user`), and the `redo` choice (all of it, or just a part).
- Money is INR in paise, as an integer.
- A `Product` needs at least one buy or rent route, and image permission unless it is a development product (`catalog_stage: development`), which only development and closed-test builds show.
- A `Brief` may carry `taste_answers`: the styles, swipes, budget and must-haves as the person answered them. The brief's own `budget` and `must_haves` are what the engine applies.
- A `Product` needs image permission and at least one buy or rent route.
- A `DesignItem` is placed by the solver or the user, never by a model.
- A `Render` is always marked illustrative. On a photo room it is a `composite` (the photo with removed things taken out and products placed by code; it always renders) or a `composite_lit` (the composite with a light-only pass, shown only when its checks pass). A `Design` may carry the room's `measurement_level`; at `estimated` the whole design is illustrative and no item carries a fit. On a photo room a `Design` records its `layout_rung`: the rung of the fallback ladder (standard, floating sofa, side-wall sofa, smaller seating, refresh) that made it.
- A room is a floor polygon, not a box. `shell.walls` are its edges in order; an edge's optional `kind` says what is there: `wall` (the default, a wall was seen), `open` (seen to have no wall: a doorway or the way into the next area; passable) or `unseen` (no photo or scan showed it; never called open, nothing placed against it, nobody routed through it). Nothing is placed against an open or unseen edge.
- A `SpaceTwin` is never edited. A `Design` points at a twin id and version plus ordered `TwinEdit`s (move, rotate, remove, replace, add, restyle a surface), made by the user or the solver, never a model. `applyEdits` and `spaceProfileFromTwin` in `@sajao/schemas/twin` derive the edited twin and the `SpaceProfile`.
- A `SpaceTwin` names where it may be shown from: `viewing.hero_views` (real keyframe poses, picked by code) and `viewing.safe_region`. A hero view points at a keyframe and has no pose of its own. `heroKeyframes`, `insideSafeRegion` and `clampToSafeRegion` in `@sajao/schemas/twin` are what a viewer uses.
- A hero mask may carry its `outline`: closed polygons on the photo in shares of its width and height (`ImagePoint`), so the app draws a tapped thing without fetching its mask.
- `direction` is optional on a `SpaceTwin` and a `SpaceProfile`: a room from gallery photos has no compass reading. Without it Vastu stays off until the person confirms a direction.
- A twin object's size is its measured box; a generated 3D model is scaled to the box and never sets the size. Replaced and added items take their catalog size.
- A `RoomStatus` has one `stage` (`uploaded`, `reading`, `designing`, `rendering`, `ready`, `failed`). A `failure` with a machine-readable `reason` is present exactly when the stage is `failed`. It carries the twin's `confidence_level` once the room is read, and for every design item whether a fit check ran (`fit_checked`, never true on an estimated room).
- Unknown properties are rejected everywhere except `Event.properties`.

## Changing the contract

A schema change is its own pull request.

1. Edit the source in `schemas/v1`. Within v1, only add optional fields; anything else needs a new major version directory.
2. Run `pnpm --filter @sajao/schemas generate` and commit the generated files.
3. Add or update fixtures in `fixtures/v1` (`valid/<object>.json`, `invalid/<object>.<case>.json`).
4. Run `pnpm --filter @sajao/schemas test` and `uv run pytest packages/schemas`.

CI regenerates and fails if the committed output is stale.

## Using it

- TypeScript types: `import type { Design } from "@sajao/schemas"`.
- TypeScript validation at a boundary: `import { validate } from "@sajao/schemas/validate"`.
- Python: `from sajao_schemas import Design, to_json_dict`.
