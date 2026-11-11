# Design engine: how the 3 variations are made

The engine is a pipeline of small, testable steps. Only step 1 touches an LLM, and step 6 guarantees nothing wrong reaches her.

1. **Brief to spec.** A small LLM turns the form and free text into a strict JSON spec: categories and counts, budget split, palette, constraints. The output is schema-checked; a bad output is retried or falls back to form values alone.
2. **Style vector.** Swiped photos and reference images are embedded with an open vision model and averaged. No LLM call.
3. **Furniture program.** Rule templates per room type decide what the room needs. Example: living room, 4 seats, TV, means a 3-seater plus 2 chairs or an L-sofa, a TV unit, a centre table, a rug.
4. **Candidate retrieval.** Vector search for style match, then hard filters: category, price, in stock at her pincode, and maximum size the room can take. Returns about 30 options per slot.
5. **Layout solver.** Places items by optimisation (OR-Tools or simulated annealing over positions and rotations). Runs on CPU in a few seconds.
6. **Verifier.** Independent code re-checks every hard rule, the budget sum and stock. A failed design is discarded and never shown.
7. **Ranker.** Orders the surviving designs. Starts as hand-set weights, becomes a learned model.

| Hard rules (never broken) | Soft scores (traded off, later learned) |
| --- | --- |
| Everything inside the room, nothing overlapping | Focal point and symmetry |
| Door swings and window access clear | Conversation distance of 1.5 to 3 m between seats |
| Walkways at least 75 cm | TV viewing distance matched to screen size |
| Switchboards, sockets and AC airflow not blocked | Daylight on desks, no glare on screens |
| Wardrobe and drawer opening clearance | Rug under the front legs of seating |
| Total price within budget | Style and palette match |
| Only verified-dimension items in tight spots | Vastu preference, when switched on |

The three variations differ by design, not by random seed. Each must use a different layout archetype or change at least half of the large pieces, so she gets three real choices.

The "why this works" notes under each design are generated from the solver's own score terms with templates. They are true by construction and cost nothing.
