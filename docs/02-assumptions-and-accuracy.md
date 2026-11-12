# Assumptions and accuracy

Zero error is not achievable. What is achievable is a known error band, shown to the user, and a system that never makes a fit claim it cannot back.

## Why the tape sets the numbers

Typical Indian "before" rooms are white walls and glossy vitrified tile: the hardest surfaces for camera reconstruction. A scan taken by turning in place adds almost no parallax. Even a good 2 to 3% reconstruction error is 8 to 12 cm on a 4 m wall, which is too much to back fit claims in small rooms, and one tape measurement fixes scale but not shape distortion. So:

- **Dimensions come from the tape:** length, width, ceiling height, and any extra wall segment of a non-rectangular room. Accuracy is about 1 cm.
- **The scan proposes everything else:** room shape, door and window positions, existing items, wall and floor masks, camera positions for renders and reels. She confirms by dragging.
- **Reconstruction-only measuring is a phase 0 experiment** (unvalidated). If it meets the gate in the roadmap, the tape can become optional later.

## Engineering rules

| Rule | What it means in the product |
| --- | --- |
| Every number carries a source | Each dimension is tagged measured, user-confirmed or estimated. Only measured and user-confirmed values can back a "fits" claim. |
| Fit uses a safety margin | Clearances add the error band of every value involved. Estimated door and window positions carry a 10 cm margin. |
| Ask instead of guess | A tight spot near an estimated value triggers one targeted measurement request. |
| Nothing unverified ships | The verifier re-tests collisions, clearances, budget and stock on every design. |
| Renders never claim exactness | The photo render is illustrative; exact layout and sizes live in the 3D view. |
| Direction is cross-checked | Vastu advice uses compass, building outline and user confirmation together. |

## Targets (gates live in the roadmap)

| Measure | Target |
| --- | --- |
| Room dimensions from tape entry | Median error 1% or less, 90th percentile 2% or less against golden truth |
| Door and window position from scan, after confirm | Median error 10 cm or less |
| Room orientation for Vastu | Within 10 degrees when the building outline is found (unvalidated) |
| Product dimension accuracy | 99% of audited items match the brand's listing |
