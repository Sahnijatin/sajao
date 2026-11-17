# Photos path for phones without AR: wall error

Question: from a handful of photos (no AR poses, no LiDAR) plus one tape value, how close are the walls?

Method (`gpu/photos_eval.py`, run with `modal run gpu/app.py::photos`):

1. Pick n photos from each ARKitScenes room, spread by view direction (AR poses only choose them).
2. MapAnything (Apache weights) gives each photo a camera from images and intrinsics only.
3. MoGe-3 depth gives metric scale (`twin.photos.metric_scale`); the cameras' mean up levels the room (`level_rotation`).
4. The production `fit_space` fits the walls from MoGe-3 points, with `depth_source="image"`.
5. One tape value, the true length of the longest wall, rescales everything (`tape_factor`).

Reference: the room fitted from LiDAR depth on AR poses (120 frames). These are ARKitScenes rooms scored against LiDAR, not golden rooms with tape: the golden set has no rooms yet.

## Results

Error on the other wall pair once the tape value is applied to the right wall (five rooms):

| Poses | Wall fit | Photos | Per room | Median abs |
| --- | --- | --- | --- | --- |
| AR (diagnosis) | percentile (production) | 15 | -19, +17, -9, -44, -13 | 17% |
| AR (diagnosis) | dense layer | 15 | +9, +8, +9, -17, -12 | 9% |
| MapAnything | dense layer | 15 | +14, +7, +61, +17, -40 | 17% |
| MapAnything | percentile (production) | 40 | +66, +29, -10, -30, +6 | 29% |

Ceilings, before tape: within 5% on four of five rooms with AR poses; 10% to 19% too high with MapAnything poses.

Matching the tape value to a wall by length (`tape_factor` picks the nearest) often picks the wrong wall, because the fitted shape is distorted; errors after it reach 60% to 120%. The tape value must name its wall.

## What this says

- Even with true poses, image depth stretches or shrinks one wall pair by about 10%: MoGe-3 sees through doors and windows (the percentile fit stretches), and the dense-layer fit stops at furniture fronts (it shrinks).
- Predicted poses add more: median 17%, worst 61%, on the wall the tape does not touch.
- One tape value fixes scale, not shape. At 17% median error a 4 m wall is off by about 0.7 m: not enough to decide fit.

Nothing relies on this path. Options for a decision are on the Notion task.
