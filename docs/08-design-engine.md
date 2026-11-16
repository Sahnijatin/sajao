# Design engine

A language model proposes, a solver places, a verifier decides. The engine is CPU-only apart from model calls, so it is cheap and deterministic where it matters.

## Steps

1. **Brief to spec.** A language model turns the Space Profile, Taste Profile and Brief into a strict JSON spec: furniture program, palette, lighting layers, budget split. Schema-checked; on failure, retry once, then fall back to rules.
2. **Retrieval.** Hard filters first (category, price, stock at your pincode, maximum size the room can take with margin), then ranking by the taste vector. About 30 candidates per slot.
3. **AI designer.** Picks a coherent set from the shortlist only (never invents products), checks colour harmony in a perceptual colour space, chooses wall paint and flooring, and seeds a layout archetype.
4. **Solver.** OR-Tools plus simulated annealing places items against wall, door, window, walkway and Vastu constraints, with the room's error band as extra margin.
5. **Verifier.** Independent re-check of every hard rule, budget and stock. Failures go back to the designer with the exact violations, or through the relaxation order.
6. **Three intents.** Best value (about 80% of budget), Best match (at budget), Bold (different archetype, up to 10% over). The three must differ in archetype or in at least half the large pieces.
7. **Honest result.** If nothing fits, you see what does fit and why, with one-tap brief changes.

## Relaxation order

When no design passes, the engine relaxes in this order and stops at the first step that yields a verified design:

1. Drop optional items (extra decor, second accent chair, side table).
2. Choose smaller products in the same categories.
3. Switch layout archetype.
4. Reduce walkway width from 75 cm toward the 60 cm hard minimum.
5. Reduce the furniture program (for example, 3-seater to 2-seater, queen to double bed).

**Never relaxed:** door swings, window access, the 60 cm walkway minimum, switchboard and AC access, wardrobe and drawer opening clearance, budget when set to strict. Every relaxation used is shown on the design.

## Rules

| Hard rules (never broken) | Soft scores (traded off) |
| --- | --- |
| Everything inside the room with error-band margin, nothing overlapping | Focal point and balance |
| Door swings and window access clear | Conversation distance 1.5 to 3 m |
| Walkways at least 60 cm (75 cm preferred, scored) | TV viewing distance |
| Switchboards, sockets and AC airflow not blocked | Rug under the front legs of seating |
| Wardrobe and drawer opening clearance | Style and palette match to the taste vector |
| Budget within limit when strict | Layered lighting present |
| Only verified-dimension items in tight spots | Plants, rug and art present unless switched off |
| Strict Vastu rules, when strict mode is on | Vastu guidance score |

## Archetypes

Start with 10 to 12 layout archetypes each for living rooms and bedrooms, grown from real failures. Archetypes cover the repeated layouts of Indian flats. Balconies, other spaces and partial scans (a corner or one wall) use a lighter template set, labelled as such on the design, until golden-set tests pass. When you choose "Just a part", the solver places new items only inside the area you drew and treats the rest of the space as fixed.

## Explanations

"Why this works" notes are generated from the solver's own scores (clearance, symmetry, light, Vastu points met), never invented.

## Rearrange only

The same engine with your existing items as the catalog.

## Chat (Next tier)

"Make it cosier" or "cheaper sofa" become spec edits that run through the same solver and verifier.
