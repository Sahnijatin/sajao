# Room capture

Capture works on any phone with a camera. Phone hardware can make the scan faster or sharper, but accuracy never depends on it.

## What she does

1. Stands near the middle of the room and turns slowly through a full circle, like a panorama.
2. Does a short second sweep from the doorway.
3. Measures one highlighted wall with a tape.

No corner-by-corner or wall-by-wall measuring.

## What the screen shows while she scans

| Element | How it works | Phones |
| --- | --- | --- |
| Level line, green or red | Tilt sensor; green when the phone is upright at chest height | All |
| Speed gauge | Gyroscope; "slow down" when turning too fast | All |
| Traced room edges | On-device edge detection on camera frames highlights wall corners and the ceiling line; they glow once captured | All |
| Coverage ring | Fills as directions are covered | All |
| Corner ticks | Each corner captured lands with a light haptic tap | All |
| Scanning grid | Live mesh grid painted on detected floor and wall planes | ARCore and ARKit phones |
| Scanning grid, fallback | Grid sweeps in along the traced edges, matching real coverage | Older phones |
| Warnings | Low light, blur, mirrors and glass, too close | All |

All overlays are translucent glass over the camera. Short text with icons, optional voice prompts in Hindi and English.

**Photo mode** for the weakest phones: 8 to 12 guided shots with ghost outlines, "shot 3 of 10, turn right until the outlines match".

**After capture:** an on-device quality score. A weak area gets a specific retake prompt, such as "retake the corner near the window".

## What happens on the server

1. The phone uploads the 30 to 60 sharpest frames with motion data and compass headings (about 5 to 10 MB, resumable).
2. **Reconstruction** rebuilds metric 3D from the frames. Candidates: MapAnything (Apache 2.0 release) and VGGT (commercial checkpoint). Both are benchmarked on the golden set; the better one ships. Depth Anything 3 Base, Small or Metric (Apache 2.0) can assist with depth.
3. **Boosters when present:** ARCore or ARKit tracking poses are sent as extra input. On LiDAR iPhones, Apple RoomPlan builds the room on the device.
4. **Layout extraction** fits walls, floor, ceiling, doors and windows into a clean plan.
5. **Segmentation** with SAM 3 (text-prompted, commercial license) finds existing furniture and produces exact wall, floor and window masks on her photos for paint, flooring and render steps.
6. **Scale lock:** the tape value on the highlighted wall scales the room. If the reconstruction's own scale disagrees by more than the tolerance, one more measurement is requested. Conflicts are never averaged away.

## The room model

One JSON scene graph, versioned in `packages/schemas`: walls, floor polygon, ceiling height, doors with swing, windows with sill height, fixed elements (AC, switchboards, sockets, beams), existing furniture as labelled boxes with keep, replace or remove, wall and floor materials, camera poses for every kept frame, compass heading and building orientation, and a confidence value plus source tag on every element.

Quality gates: walls close into a polygon within tolerance; ceiling 2.4 to 3.3 m; door width 0.7 to 1.1 m; scale agreement within tolerance.

## Running well on old phones

| Constraint | Answer |
| --- | --- |
| 2 to 4 GB RAM, slow chip | No on-device AI. Edge detection and sharpness checks are lightweight frame processors. |
| Weak GPU | Three viewer tiers chosen automatically: full 3D, lite 3D, 2D plan with product cards |
| Slow data | Small uploads, compressed assets on demand, designs cached offline |
| Old OS versions | Support as far back as the framework allows; confirm minimums at setup |

Later: a flat-type library. Flats in the same tower share layouts, so one verified scan can serve every neighbour.
