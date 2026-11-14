# Engineering rules

Every change to Sajao follows these rules. Breaking one requires a decision log entry with a reason first.

## Scope

1. Work starts only from a task in the current sprint. Anything else is out of scope by default.
2. A needed change outside scope is proposed as a scope change and waits for founder approval before any code, task or doc edit.
3. Deep before wide: finish the current tier before starting the next.

## Product truth

4. Generative models never set a dimension, position, rotation, price or stock value. Geometry models estimate; tape verifies; code decides fit.
5. Every dimension carries a value, a source (measured, estimated, user-confirmed) and an error band. The solver uses the band as margin.
6. Every design passes the verifier before it reaches a user. When none passes, follow the relaxation order, then show an honest result.
7. The render, the plan and the shopping list are derived from one `Design` object and are cross-checked: render to plan (grounding), render to cart (likeness), plan to cart (dimensions, budget, stock).
8. Renders are labelled illustrative and pass structure, grounding, likeness and aesthetic checks, or the 3D render is shown. Never a broken image.
9. Every product has a permitted affiliate or rental route and permission to use its images. Buy links go through our redirect service.
10. No paywall, lock, upgrade prompt or paid badge appears in the app until the founder switches entitlements on.
11. Vastu advice is labelled guidance; strict mode runs only when direction is confirmed by more than the compass.

## Code

12. Schemas in `packages/schemas` are the contract; validate at every boundary. Schema changes are their own reviewed change.
13. All model calls go through the model gateway: primary, fallback, caps, caching, logging. The app degrades, it never stops suddenly.
14. Every model output is validated: schema for text, geometry for layouts, image checks for renders.
15. Prompts and model versions are pinned in the repo. Changing either reruns the golden-set evaluations.
16. Every model has a recorded commercial license; every external data source has a recorded permission.
17. The solver, verifier and relaxation order are pure, deterministic and property-tested.
18. Every write endpoint accepts an idempotency key. Pipeline steps are durable and resume where they stopped.
19. Expensive endpoints require app attestation and respect per-user, per-device and global spend caps.
20. Database changes go only through migrations in the repo and are backward compatible (expand, then contract).
21. Fast-tier tests must pass to merge. Changes reach `main` only through pull requests. Secrets never enter the repository, logs or chat.

## Experience

22. Every screen uses the theme package, motion presets and haptic map, and works on the budget Android in the device matrix.
23. Reduced motion is respected. Low-tier phones get lighter effects, never broken ones.
24. Strings are externalised (English and Hindi); dimensions in cm or feet and inches by user choice; prices in INR.

## Privacy

25. Raw capture video is deleted after processing; faces and personal photos are blurred in anything stored; training use requires consent.

## Repository hygiene

26. No em dashes. Use "license". Gender-neutral copy ("you", "they").
27. No personal names in text, code, commits or pull requests. No mention of tools used to write the code. No calendar dates in repo docs.
