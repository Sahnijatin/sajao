# Engineering rules

Every change to Sajao follows these rules. Breaking one requires a decision log entry first.

## Product truth

1. No language or image model ever sets a dimension, position or rotation. Geometry comes from measurement and code.
2. Every design passes the verifier before it reaches a user. A failed design is never shown.
3. Only verified-dimension products may back a "fits" claim or sit in tight spots.
4. Photo renders are conditioned on our geometry and pass the per-item fidelity check, or the 3D view is shown instead.
5. Every product listed has an app-safe affiliate route; buy links open in a browser tab we control.
6. No paywall, lock, upgrade prompt or paid badge appears in the app until the entitlement switch is turned on.
7. Vastu advice is labelled as guidance. Strict mode only runs when direction is confirmed.

## Code

8. Schemas in `packages/schemas` are the contract. Validate at every boundary.
9. All model calls go through the model gateway: caching, caps, cost logging, provider swap in one place.
10. Every model output is validated: schema checks for text, geometry checks for layouts, similarity checks for images.
11. Every model in the pipeline has a confirmed commercial license recorded in the docs.
12. The evaluation suite runs on every change; any slice getting worse blocks the merge.
13. The solver and verifier are pure, deterministic and covered by property tests.
14. Secrets never enter the repository.

## Experience

15. Every screen works on the budget Android in the device matrix.
16. Motion and haptics follow [the design language](docs/10-design-language-and-motion.md); reduced motion is respected.
17. No spinner where a meaningful progress animation is possible.

## Privacy

18. Raw capture video is deleted after reconstruction.
19. Faces and personal photos are blurred in anything stored.
20. User data is used for training only with consent.

## Repository hygiene

21. Client-facing text, commits and pull requests contain no personal names and no mention of tools used to write the code.
