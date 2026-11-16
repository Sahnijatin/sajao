# Principles and scope

## Principles

1. **AI decides taste and appearance; geometry and code decide fit; everything is checked before you see it.**
2. **One Design object.** The render, the plan and the shopping list are views of one `Design`. If they can disagree, the design is wrong.
3. **Estimate honestly, verify optionally.** Photos give estimated dimensions with an error band; tape values make them Verified. The solver always uses the band as margin.
4. **Ingest widely, show narrowly.** Thousands of products come in; only curated, verified items appear in designs.
5. **Never a broken experience.** Every model call has a fallback; every render has a 3D fallback; every infeasible brief gets an honest result.
6. **Design quality from day one.** No screen merges without the theme package, motion and haptics.
7. **Built to scale without a rebuild.** Stateless services, durable jobs, standard Postgres, one model gateway.

## The Design object

A `Design` holds the room it belongs to, the chosen products (real SKUs with dimensions, price, stock and links), each item's position and rotation in metres, paint and flooring materials, the lighting scheme, the total cost and a check report.

| Non-negotiable | Enforced by |
| --- | --- |
| Visual quality | Guided render from your photo with the exact product photos as references; aesthetic judge; retry before you see it |
| Spatial credibility | Solver placement on the room with error-band margin; verifier on collisions, walkways, doors, windows and margins; grounding check on the render |
| Commercial utility | Live SKUs with price, stock and link; totals from the same list the render shows; budget and stock re-checked at reveal |

Honesty labels: "Illustrative render" on images, "Estimated ±X cm" on unverified dimensions, "Fits with Y cm to spare" only when the margin covers the error band.

## Tiers

| Tier | Contents |
| --- | --- |
| Must (store launch) | Photo or video capture of any space at any extent, with guides and a live scan mesh; Space Profile with detected space type, "all of it or just a part", confirm and optional tape; taste profile with adaptive swipes; three designs with three intents; guided render with checks and 3D fallback; dimensioned 2D plan with drag and rotate; shopping list with buy and rent links; basic Vastu tab; share reel; save and history; login with guest first; English and Hindi |
| Next | 3D dollhouse view on capable phones; several rooms joined into one home; rental prices; push when renders finish; web viewer for shared designs; reference images for taste; design chat ("make it cosier"); whole-home Vastu from floor plans; Vastu expert call; subscription switched on; full template sets for every space type once golden-set tests pass |
| Later | Vastu home visit; own trained taste and ranking models; carpentry and built-ins |

Nothing is picked up front: you scan whatever you want redone (a whole room, a corner, a balcony) and the app works out what it is and how much of it there is. Living rooms and bedrooms are the quality bar at launch; other spaces ship with a lighter template set, labelled as such, until golden-set tests pass. Rearrange-only mode uses the same journey with your existing items as the catalog.
