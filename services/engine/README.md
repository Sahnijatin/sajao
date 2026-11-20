# Design engine

The deterministic half of the design engine: pure Python, no GPU, no model calls, no I/O. Inputs and outputs are contract objects from `sajao_schemas`; the capture pipeline calls these functions as durable steps.

## Room shape

A room is its floor polygon. Each stretch of the polygon's edge is a wall when one of the twin's walls runs along it, and open when none does (30 cm or more): an open plan, an archway with no door, or the rest of a bigger space in a partial scan. L shapes and any other simple polygon work the same way.

- **Open edges are passable.** They never limit a walkway, and every open edge at least 60 cm long is a way in that the walkways must join, like a door.
- **Open edges are not walls.** Nothing is placed against them, wall items never hang on them, and they never box an item into a tight spot. Items still stay inside the area by the edge's band (the largest band of the walls that meet it).
- **Confidence level.** `taped`, `ar_measured` or `estimated`, passed in by the pipeline; without it, a room whose walls and ceiling are all measured reads as taped and anything else as estimated. Taped and AR-measured rooms are verified with their bands as margin and get fit claims: per-item fit (`fits`, `tight`, `does_not_fit` with the spare clearance) and "fits with N cm to spare". An estimated room is placed and verified at nominal sizes (its lengths and kept boxes without bands) with a 6 cm clearance at each wall, and its design says to measure to confirm.

## Verifier

`sajao_engine.verifier.verify(design, twin, brief, redo=..., checked_at=...)` re-checks a finished `Design` from scratch and returns its `CheckReport`, a list of violations (rule, items, detail) for the designer and the relaxation order, and each item's smallest gap. It reads only the design, the twin it builds on and the brief; it never trusts the solver.

- **Footprints.** Each item's footprint is the product's catalog width and depth plus their error bands, at the item's position and rotation. Kept twin objects and built-ins use their measured boxes plus bands. Twin edits on the design (remove, move, rotate, replace) are applied first.
- **Walls.** On a taped or AR-measured room a wall may sit anywhere within the error band of the walls that meet it, so a footprint must stay that far from it. On an estimated room each wall keeps a fixed 6 cm clearance.
- **Edges.** An edge is a `wall`, `open` (seen to have no wall: passable, an entrance) or `unseen` (no photo showed it: kept clear of by the same clearance, never placed against, never an entrance). Seating never goes against the wall of a kept TV.
- **Photo rooms: the fallback ladder.** New items go only where the photo shows floor. When no standard layout verifies there, each intent steps down, stopping at the first rung that verifies: a sofa floating toward the kept TV, with a walkway at the nominal width behind it where its back faces an open edge (it may sit to one side of the TV, still square on); a sofa on a side wall at a right angle to the TV; a two seater or armchairs; then a refresh that keeps the existing seating and adds a rug, lighting, a side table, art and plants around it. The rung is on the design (`layout_rung`). Only a failed refresh fails the request, as `needs_wider_view`. Rules may target a kept thing (`kept:tv`, `kept:seating`) as if it were placed. Everything stays at the estimated level.
- **Zones.** Door swings (inward doors, the arc covered from outside), a 60 cm approach inside every door, open edges kept to their band, 50 cm in front of every window (nothing taller than the sill), switchboards (nothing that covers them) and AC units (nothing near their height within 1 m), each grown by the bands of the numbers behind it.
- **Walkways.** Standing positions are sampled every 2.5 cm and each one's gap to walls and footprints is exact, so a corridor is never invented. The doors and open edges must be joined by walkways at least 60 cm wide, and every seat, bed side, wardrobe, drawer front and kept cupboard must be within 45 cm of those walkways. 75 cm walkways are scored, not required.

| Hard rule | Fails when |
| --- | --- |
| `twin_matches_items` | An item has no add edit with its product and pose, or an edit has no item, or the twin id or version differs |
| `total_matches_items` | The total is not the sum of the item prices |
| `inside_room` | A footprint leaves the floor or comes closer to a wall than the wall's band |
| `inside_redo_area` | An item is outside the part the user chose to redo |
| `no_overlap` | Two floor footprints share area, or a footprint overlaps a kept item; rugs only clash with rugs |
| `door_clear` | Anything is in a door swing, or anything but a rug is in a door approach |
| `window_access` | Anything taller than the sill stands in front of a window |
| `fixture_access` | Something tall enough to cover it stands at a switchboard or under an AC unit |
| `front_clearance` | A wardrobe, drawer or seat front is blocked (wardrobe 60 cm, dresser 50 cm, sideboard 45 cm, TV unit 40 cm, seats 30 cm) |
| `wall_items_clear` | A wall item is not on a wall, runs past it, or covers a door or window (curtains may cover windows) |
| `walkway_min` | A door or a needed item cannot be reached by a 60 cm walkway |
| `tight_spots_measured` | An item with an estimated size is boxed in on both sides of an axis with less than 5 cm to spare |

`passed` is true only when every hard rule, the budget (strict, or up to 10% over with `stretch_10`) and the stock check pass.

## Archetypes

`sajao_engine.archetypes` holds the layout archetypes as data: ordered slots, each with the categories it takes, whether it is required, and a placement rule (against a wall, in a corner, in front of, facing, at the side of, beside, in a free corner, a rug under, art above, a light over, on top of). Eight for living rooms and eight for bedrooms; `for_space` returns none for other spaces, which get no designs at launch.

## Solver

`sajao_engine.solver.place(PlacementRequest) -> PlacementResult` places the products the designer chose for an archetype's slots and returns a `Design` that the verifier has passed, or what stopped it.

- **Search.** Slots in archetype order. Each rule proposes poses (10 cm steps along walls, gaps from the rule), cheap local hard checks drop impossible ones, a soft score (rule fit, no dead gaps narrower than a walkway) ranks them, and the best 8 partial layouts go on, at most 2 per wall so one bad wall choice cannot sink the search. After every floor item a coarse walkway check (5 cm) prunes layouts that already cut a door off.
- **Gate.** The best 6 complete layouts go to the verifier at 2.5 cm; the best that passes, with a bonus for 75 cm walkways, becomes the Design. Twin edits remove what the brief does not keep and add every item with its catalog size.
- **Honest failure.** Optional slots with no place are dropped and recorded; a required slot with no place stops the search and is named.

Runs in 0.1 to 2.5 s per room on one CPU on the fixture rooms.

## Relaxation order

`sajao_engine.relax.design_with_relaxation(DesignRequest) -> EngineResult` runs the solver, then relaxes in the documented order (drop optional items, smaller products in the same size class, switch archetype, aim for 60 cm instead of 75 cm walkways, reduce the program), keeping each step, and stops at the first verified design. Every relaxation used is on the design. When none passes, the result says what fits, why the rest does not (from the attempts' own findings) and which brief changes would help: a tape measure when the scan's bands are wide, a smaller piece, a higher budget, fewer pieces, or letting a kept item go. A strict budget is never relaxed.

## Categories

`sajao_engine.categories` says how each product category sits (floor, rug, wall, ceiling, on another item), which sides must be reached and how much clear floor its doors and drawers need. Unknown categories are plain floor furniture.

## Fixtures

`sajao_engine.testing.fixture_rooms()` returns the commonest Indian flat layouts as full `SpaceTwin`s (2BHK and 3BHK halls, a compact 1BHK hall, an L-shaped hall, master, standard and small bedrooms), open-plan rooms from `open_plan_rooms()` (a hall open to the dining area, an L-shaped open living area with its kitchen side open, a hall with an archway, an L-shaped bedroom), plus the schema's own twin fixture. `twin_from_polygon` takes `open_edges` and `open_spans` to leave walls out. `product`, `brief` and `design` build contract objects for tests.

## Tests

```bash
uv run pytest services/engine
```

Property tests (Hypothesis) check that a passing design has no overlap and stays inside the room, that a collision, a blocked door or a walkway under 60 cm never passes, and that the solver never returns a design that fails the verifier on random rooms.
