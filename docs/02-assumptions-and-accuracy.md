# Assumptions and accuracy

Zero error from a phone camera is not physically achievable. What is achievable is a known error band, shown to the user, and a system that never makes a fit claim it cannot back.

Working assumptions:

- India first, consumer app, affiliate-led revenue at launch.
- One room per project; whole-home layout comes from a floor plan photo, not a full scan.
- Code, not a model, is the authority on measurements.

## How "no room for error" becomes engineering rules

| Rule | What it means in the product |
| --- | --- |
| Every number carries a source | Each dimension is tagged measured, user-confirmed or estimated. Only the first two can back a "this fits" claim. |
| Fit uses a safety margin | If the scan's error band is 3 cm, an item must clear by more than 3 cm. Otherwise the app asks for one more measurement. |
| Ask instead of guess | Low confidence triggers one targeted request, never a silent guess. |
| Nothing unverified ships | The verifier re-tests collisions, clearances, budget and stock on every design. |
| Renders cannot drift | Photo renders are conditioned on our geometry and checked item by item against the real product photo. |
| Direction is cross-checked | Vastu advice uses compass, building outline and user confirmation together. |

## Targets to validate on the golden set (not promises)

| Measure | Target |
| --- | --- |
| Wall length, any phone, after one tape check | Within 2 to 3% |
| Wall length, LiDAR iPhone | Within 1 to 3 cm |
| Door and window position | Within 5 cm |
| Room orientation for Vastu | Within a few degrees when the building outline is found; flagged as approximate otherwise |
| Product dimension accuracy | 99% of audited items match the brand's listing |
