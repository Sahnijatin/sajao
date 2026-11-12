# Engineering rules

Every change to Sajao follows these rules. Breaking one requires a decision log entry with a reason first.

## Scope

1. Build only the current tier of the cut line in `docs/01-bottom-line.md`. Deep before wide.
2. Claims marked unvalidated are hypotheses. Do not build on them until phase 0 replaces them with measured results.

## Product truth

3. Room dimensions come from tape entry. No language or image model ever sets a dimension, position or rotation.
4. Every design passes the verifier before it reaches a user. When none passes, follow the relaxation order, then show an honest result.
5. Only verified-dimension products may back a "fits" claim or sit in tight spots.
6. Photo renders are labelled illustrative and pass the outline and likeness checks, or the 3D render is shown.
7. Every product has a permitted affiliate route and permission to use its images; buy links open in a browser tab we control.
8. No paywall, lock, upgrade prompt or paid badge appears in the app until the entitlement switch is turned on.
9. Vastu advice is labelled guidance; strict mode runs only when direction is confirmed.

## Code

10. Schemas in `packages/schemas` are the contract; validate at every boundary.
11. All model calls go through the model gateway with its fallback chain. The app never stops suddenly; it degrades.
12. Every model output is validated: schema for text, geometry for layouts, outline and similarity for images.
13. Every model has a recorded commercial license; every external data source has a recorded permission.
14. Fast-tier tests must pass to merge. Nightly and release tiers are reviewed with confidence intervals.
15. The solver, verifier and relaxation order are pure, deterministic and property-tested.
16. Changes reach `main` only through pull requests. Secrets never enter the repository.

## Experience

17. Every screen works on the budget Android in the device matrix.
18. Motion and haptics follow `docs/10-design-language-and-motion.md`; reduced motion is respected.
19. No spinner where a meaningful progress animation is possible. No time promises until measured.

## Privacy

20. Raw capture video is deleted after processing; faces and personal photos are blurred in anything stored; training use requires consent.

## Repository hygiene

21. Text, commits and pull requests contain no personal names and no mention of tools used to write the code.
