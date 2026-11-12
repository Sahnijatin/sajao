# Design engine

The engine is a loop of small, testable steps. Language and vision models propose and critique; the solver and verifier decide. Research on room-design agents shows iteration only improves layouts when grounded checking tools are in the loop; without them, revisions make layouts worse. Our loop is built around that finding.

## Steps

1. **Brief to spec.** A language model turns the brief and free text into a strict JSON spec. Schema-checked; a bad output is retried or falls back to form values.
2. **Functional constraints.** Who uses the room and for what (persona, activities, household) becomes constraints in four groups: spatial, ergonomic, activity, environmental. Vastu adds a fifth group when switched on.
3. **Style target.** The chosen style profile plus any reference images become a target in embedding space.
4. **Candidate retrieval.** Hard filters (category, price, stock at her pincode, maximum size the room can take), then style match and the "goes together" compatibility model. About 30 options per slot.
5. **AI designer.** Proposes the furniture program, what goes next to what, lighting layers, wall and floor treatments, and product picks from the shortlist only. Seeded with a layout archetype.
6. **Solver.** Places items by optimisation (OR-Tools and simulated annealing over positions and rotations) starting from archetype templates. CPU, seconds.
7. **Verifier.** Independent code re-checks every hard rule, the budget sum and stock. A failed design goes back to the designer with the exact violations.
8. **Critique and repair.** Each passing design is rendered (top view plus a camera view). The AI judge scores it against a fixed rubric; the designer repairs the weakest points. Capped at a few rounds.
9. **Ranking.** The taste ranker orders surviving designs. The three shown must differ in layout archetype or change at least half the large pieces.

If any model call fails, the engine falls back to templates plus rules, so a design is always produced.

## Archetypes

Indian flats repeat a limited set of room shapes. Instead of learning design from scratch, the engine uses 30 to 50 designer-authored layout archetypes per room type (for example: sofa on the longest wall facing the TV wall; L-sofa in the corner; bed head on the solid wall with side tables). Coverage is measured: the share of real scanned rooms where an archetype fits without violations. Rooms that fail become new archetypes.

## Rules

| Hard rules (never broken) | Soft scores (traded off) |
| --- | --- |
| Everything inside the room, nothing overlapping | Focal point and balance |
| Door swings and window access clear | Conversation distance 1.5 to 3 m between seats |
| Walkways at least 75 cm | TV viewing distance matched to screen size |
| Switchboards, sockets and AC airflow not blocked | Daylight on desks, no glare on screens |
| Wardrobe and drawer opening clearance | Rug under the front legs of seating |
| Total price within budget | Style and palette match |
| Only verified-dimension items in tight spots | Layered lighting: ambient, task and accent present |
| Strict Vastu rules, when strict mode is on | Plants, rug and art present unless switched off |
| | Vastu guidance score, when guidance mode is on |

"Why this works" notes under each design are generated from the solver's own score terms with templates, so they are true by construction.

Chat uses the same loop: "make it warmer" or "cheaper sofa" becomes a designer instruction with tool calls (swap, move, set budget, change palette, lock, regenerate), and every result passes the verifier.
