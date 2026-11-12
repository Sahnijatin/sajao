# Room capture

The tape sets the numbers; the scan does everything else. Capture works on any phone with a camera.

## What she does

1. **Walks a slow loop around the room** with the phone pointed across the room at the opposite walls. Walking (not turning in place) gives the parallax reconstruction needs.
2. **Measures** length, width and ceiling height with a tape when the app highlights each one on the drafted plan. About one to two minutes.
3. **Confirms** doors, windows and existing items by dragging and tapping.

## What the screen shows while she scans

| Element | How it works | Phones |
| --- | --- | --- |
| Level line, green or red | Tilt sensor; green when upright at chest height | All |
| Speed gauge | Gyroscope and frame blur; "slow down" | All |
| Traced room edges | On-device edge detection highlights wall corners and the ceiling line; they glow once captured | All |
| Coverage ring | Fills as walls are covered from enough positions | All |
| Corner ticks | Light haptic tap per captured corner | All |
| Scanning grid | Live grid painted on detected floor and wall planes | ARCore and ARKit phones |
| Scanning grid, fallback | Grid sweeps in along traced edges, matching real coverage | Older phones |
| Warnings | Low light, blur, mirrors and glass, too close | All |

Overlays are translucent glass over the camera, with short text, icons and optional Hindi and English voice prompts.

## What the scan is used for

| Output | Used for | Validated? |
| --- | --- | --- |
| Proposed room shape | Drafting the plan she measures | Unvalidated |
| Door and window positions | Plan, clearances (with a 10 cm margin) | Unvalidated, gated in phase 0 |
| Existing furniture (SAM 3) | Keep, replace, remove | Unvalidated |
| Wall, floor and window masks (SAM 3) | Paint and flooring previews, renders | Unvalidated |
| Camera position of every kept frame | Photo renders and the share reel | Unvalidated |
| Compass headings | Vastu direction | Unvalidated |

## Server pipeline

1. The phone uploads the sharpest 30 to 60 frames with motion data and compass headings (about 5 to 10 MB, resumable).
2. Reconstruction (MapAnything Apache 2.0 release or the VGGT commercial checkpoint, benchmarked in phase 0) recovers camera positions and a rough room shape. ARCore or ARKit poses are added when available. LiDAR iPhones may use RoomPlan.
3. Layout extraction proposes walls, doors and windows; SAM 3 produces item and surface masks.
4. Taped values replace reconstructed dimensions. The reconstruction is fitted to the taped box so camera positions stay consistent with the measured room.

## Phase 0 experiment: can the tape become optional?

On the golden set, measure reconstruction-only room dimensions against truth for each phone tier. If the gate in the roadmap is met on a tier, tape entry can become optional on that tier later. Until then the tape is required.

## The room model

One JSON scene graph in `packages/schemas`: walls, floor polygon, ceiling height, doors with swing, windows with sill height, fixed elements (AC, switchboards, sockets, beams), existing items with keep, replace or remove, wall and floor materials, camera poses, compass heading and building orientation, and a confidence value plus source tag on every element.

Quality gates: walls close within tolerance; ceiling 2.4 to 3.3 m; door width 0.7 to 1.1 m; taped values consistent with each other.

## Old phones

No on-device AI; edge detection and sharpness checks are lightweight frame processors. Small resumable uploads. Photo mode for the weakest phones is in the Next tier.
