# Schemas

The contract between the app, the API and the workers. One JSON Schema source per journey object in `schemas/v1`; TypeScript types and Pydantic models are generated from it, so the three sides cannot drift.

| Object | Stage |
| --- | --- |
| `Capture` | Input |
| `SpaceProfile` | Understanding |
| `TasteProfile`, `Brief` | Personalisation |
| `Product` | Catalog item, embedded in a design |
| `Design` | Design |
| `Render`, `Plan`, `ShoppingList` | Views derived from one `Design` |
| `Event` | Action log |

## Rules the schemas enforce

- Every dimension is a `Dimension`: a value in metres, a source (`measured`, `estimated`, `user_confirmed`) and an error band. A test fails if a bare length is added anywhere else.
- A space is whatever was scanned: `Capture` has no room type. `SpaceProfile` carries the detected `space_type` and `extent`, who set each (`detected` or `user`), and the `redo` choice (all of it, or just a part).
- Money is INR in paise, as an integer.
- A `Product` needs image permission and at least one buy or rent route.
- A `DesignItem` is placed by the solver or the user, never by a model.
- A `Render` is always marked illustrative.
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
