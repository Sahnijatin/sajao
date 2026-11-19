# Design engine

A language model proposes, a solver places, a verifier decides. The engine is CPU-only apart from model calls, so it is cheap and deterministic where it matters.

## Steps

1. **Brief to spec.** A language model turns the Space Profile, Taste Profile and Brief into a strict JSON spec: furniture program, palette, lighting layers, budget split. Schema-checked; on failure, retry once, then fall back to rules.
2. **Retrieval.** Hard filters first (category, price, stock at your pincode, maximum size the room can take with margin), then ranking by the taste vector. About 30 candidates per slot.
3. **AI designer.** Picks a coherent set from the shortlist only (never invents products), checks colour harmony in a perceptual colour space, chooses wall paint and flooring, and seeds a layout archetype.
4. **Solver.** A deterministic beam search places the chosen products slot by slot from the archetype's rules, against wall, door, window, fixture, walkway and Vastu constraints. Taped and AR-measured rooms use their error band as extra margin; estimated rooms (from photos) are placed at nominal sizes with a 6 cm clearance at each wall. Cheap local checks and a coarse walkway check prune each step; the best complete layouts go to the verifier, and the first that passes becomes the Design. Seconds on one CPU, no randomness.
5. **Verifier.** Independent re-check of every hard rule, budget and stock, from the Design, the twin and the brief only. Footprints are catalog sizes plus their error bands; on taped and AR-measured rooms walls keep the bands of the walls that meet them, on estimated rooms a 6 cm clearance; walkways are checked on a 2.5 cm clearance grid that never overstates a gap. Failures go back to the designer with the exact violations, or through the relaxation order. Rules and thresholds: `services/engine/README.md`.
6. **Three intents.** Best value (about 80% of budget), Best match (at budget), Bold (different archetype, up to 10% over). The three must differ in archetype or in at least half the large pieces.
7. **Honest result.** If nothing fits, you see what does fit and why, with one-tap brief changes.

## Room shape and confidence

The engine takes any floor polygon, L shapes included. An edge with a wall along it is a wall; an edge with none is open. Open edges are passable (walkways must reach them like a door) and never treated as walls: nothing is placed against them. Each room has a confidence level (taped, AR-measured or estimated). Taped and AR-measured rooms are verified with their error bands as margin; estimated rooms at nominal sizes with a 6 cm clearance. Fit claims ("fits with 12 cm to spare", per-item fit) are made only for taped and AR-measured rooms; an estimated room's design asks you to measure to confirm.

## Relaxation order

When no design passes, the engine relaxes in this order and stops at the first step that yields a verified design. Steps are cumulative, and switching archetype moves down the designer's ranked list:

1. Drop optional items (extra decor, second accent chair, side table).
2. Choose smaller products in the same categories and size class (a smaller queen bed, not a double).
3. Switch layout archetype.
4. Reduce walkway width from 75 cm toward the 60 cm hard minimum.
5. Reduce the furniture program (for example, 3-seater to 2-seater, queen to double bed).

**Never relaxed:** door swings, window access, the 60 cm walkway minimum, switchboard and AC access, wardrobe and drawer opening clearance, budget when set to strict. Every relaxation used is shown on the design.

## Rules

| Hard rules (never broken) | Soft scores (traded off) |
| --- | --- |
| Everything inside the room (error-band margin on measured rooms, 6 cm on estimated ones), nothing overlapping | Focal point and balance |
| Door swings and window access clear | Conversation distance 1.5 to 3 m |
| Walkways at least 60 cm (75 cm preferred, scored) | TV viewing distance |
| Switchboards, sockets and AC airflow not blocked | Rug under the front legs of seating |
| Wardrobe and drawer opening clearance | Style and palette match to the taste vector |
| Budget within limit when strict | Layered lighting present |
| Only verified-dimension items in tight spots | Plants, rug and art present unless switched off |
| Strict Vastu rules, when strict mode is on | Vastu guidance score |

## Archetypes

Layout archetypes for living rooms and bedrooms only, grown from real failures toward 10 to 12 each. They cover the repeated layouts of Indian flats: a sofa facing the TV wall, a conversation set, an L-sofa in a corner, a sofa on the short wall of a long hall, a diwan lounge; a bed centered on the headboard wall, a bed in the corner of a small room, a study corner, a dresser or wardrobe opposite the bed. Other spaces can be scanned but get no designs at launch. The app redoes the whole captured space; "Just a part" is not offered at launch. The solver still supports a part (new items only inside a drawn area, the rest fixed) for when it returns.

## Explanations

"Why this works" notes are generated from the solver's own scores (clearance, symmetry, light, Vastu points met), never invented.

## Rearrange only

The same engine with your existing items as the catalog.

## Chat (Next tier)

"Make it cosier" or "cheaper sofa" become spec edits that run through the same solver and verifier.
