# Design engine

Language and vision models propose and critique; the solver and verifier decide. Research on room-design agents shows iteration only improves layouts when grounded checking tools are in the loop, so every step here is checked by code.

## Steps

1. **Brief to spec.** A language model turns the brief into a strict JSON spec. Schema-checked; a bad output is retried or falls back to form values.
2. **Functional constraints.** Household and activities become spatial, ergonomic, activity and environmental constraints; Vastu adds a group when on.
3. **Style target.** Style profile plus references become a target in embedding space.
4. **Candidate retrieval.** Hard filters (category, price, stock at her pincode, maximum size the room can take), then style match. About 30 options per slot.
5. **AI designer.** Proposes the furniture program, pairings, lighting layers, wall and floor treatments, and product picks from the shortlist only, seeded with a layout archetype.
6. **Solver.** Places items (OR-Tools and simulated annealing) from archetype templates. CPU, seconds.
7. **Verifier.** Re-checks every hard rule, the budget and stock. Failures go back to the designer with the exact violations, or into the relaxation order below.
8. **Critique (Next tier, optional per request).** Render, score with the AI judge, repair once. The default path is a single designer pass to keep cost and latency down.
9. **Ranking.** The three designs shown must differ in archetype or change at least half the large pieces.

If a model call fails, the engine falls back to templates plus rules.

## Relaxation order

When no design passes, the engine relaxes in this order and stops at the first step that yields a verified design:

1. Drop optional items (extra decor, second accent chair, side table).
2. Choose smaller products in the same categories.
3. Switch layout archetype.
4. Reduce walkway width from 75 cm toward the 60 cm hard minimum.
5. Reduce the furniture program (for example, 3-seater to 2-seater, queen to double bed).

**Never relaxed:** door swings, window access, the 60 cm walkway minimum, switchboard and AC access, wardrobe and drawer opening clearance, budget when set to strict.

If nothing passes, she gets an **honest result**: what the room can hold, what it cannot and why ("this room fits a 2-seater with a 60 cm walkway; a 3-seater would block the door"), with options to change the brief. Every relaxation used is shown on the design.

## Archetypes

Indian flats repeat a limited set of room shapes. The engine uses 30 to 50 designer-authored layout archetypes per room type. Coverage is measured on the layout set; rooms that fail become new archetypes.

## Rules

| Hard rules (never broken) | Soft scores (traded off) |
| --- | --- |
| Everything inside the room, nothing overlapping | Focal point and balance |
| Door swings and window access clear | Conversation distance 1.5 to 3 m |
| Walkways at least 60 cm (75 cm preferred, scored) | Walkway width toward 75 cm |
| Switchboards, sockets and AC airflow not blocked | TV viewing distance |
| Wardrobe and drawer opening clearance | Rug under the front legs of seating |
| Budget within limit when strict | Style and palette match |
| Only verified-dimension items in tight spots | Layered lighting present |
| Strict Vastu rules, when strict mode is on | Plants, rug and art present unless switched off |
| | Vastu guidance score |

"Why this works" notes come from the solver's own score terms, so they are true by construction. Chat (Next tier) uses the same tools and verifier.
