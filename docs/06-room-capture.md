# Room capture and geometry

Capture works on any phone with a camera, including old budget Androids. Phone hardware can make the scan faster, but accuracy never depends on it: the tape measure sets the scale.

**The universal path (every phone)**

1. She records a slow video sweep, or takes 8 to 12 guided photos if the phone is very weak.
2. The phone picks the 30 to 60 sharpest frames and uploads only those (about 5 to 10 MB, resumable on poor networks).
3. A cloud reconstruction model rebuilds the room's shape: walls, floor, ceiling, doors, windows, existing furniture. Newer feed-forward models such as [MapAnything](https://arxiv.org/abs/2509.13414) do this from plain images in one pass. All heavy work is in the cloud, so the phone's age does not matter.
4. The app shows the floor plan and asks for a tape measurement to lock the scale.

**The tape check**

- The app picks the wall it saw best, highlights it on the plan, and asks her to measure it. One number scales the whole room.
- It then asks for a second measurement on a different wall as a check. If the two agree within 2%, the room is marked verified and the remaining error is shown.
- If they disagree, it asks for a third or a rescan of the weak area. It never averages away a conflict silently.
- Door height and door width are offered as easy alternatives when a wall is blocked by furniture.

**Boosters, used only when the phone has them**

| Capability | Share of phones | What it adds |
| --- | --- | --- |
| Camera only | All | The universal path above |
| Gyroscope and accelerometer | Nearly all | Level guide, speed warning, coverage map during capture |
| ARCore or ARKit motion tracking | Most mid-range and newer phones | A scale estimate before the tape check, and live "you missed this corner" feedback |
| ARCore Depth API | About 800 of 1,116 listed Android device entries ([device reference](https://www.simplywise.com/blog/which-android-phones-scan-rooms/)) | Cleaner furniture boxes |
| LiDAR | iPhone and iPad Pro only | Instant on-device room model; tape check becomes optional |

The app detects capability at runtime and picks the best available path. Every path outputs the same room model, so nothing downstream changes. Manual entry (type the wall lengths, mark doors and windows) stays available as a last resort and for users who prefer it.

**The capture coach (the overlay on the camera)**

Most scan errors come from how the video is shot, so the camera screen teaches while she shoots.

- **Before the first scan:** three looping animations, about 10 seconds in total. Stand in a corner. Hold the phone upright at chest height. Turn slowly, then repeat from the opposite corner. Lights on, curtains open.
- **Live overlay, translucent over the camera:** a level line that turns green when the phone is upright; a speed gauge that says "slow down"; a ring that fills as directions are covered; four corner dots that tick off with a haptic tap; warnings for low light, blur, too close, and mirrors or glass.
- **Photo mode for the weakest phones:** numbered ghost outlines, "shot 3 of 10, turn right until the outlines match", like a panorama.
- **After capture:** an on-device quality score. If an area is weak it says exactly what to redo, such as "retake the corner near the window", instead of failing later.
- **Language:** short text plus icons and optional voice prompts, in Hindi and English first.

**The room model and its quality gates**

The output is one JSON scene graph: walls, floor polygon, ceiling height, doors with swing direction, windows with sill height, fixed elements (AC, switchboards, sockets, beams), existing furniture as labelled boxes, wall and floor colours, window direction, and a confidence value plus a source tag (measured, user-confirmed, estimated) on every element.

- Walls must close into a polygon within tolerance.
- Sanity ranges: ceiling 2.4 to 3.3 m, door width 0.7 to 1.1 m.
- Whenever a phone has AR tracking or LiDAR, compare its scale with the camera-only result. Each such scan is free ground truth that improves the universal path.
- Confirm the commercial license of any reconstruction model before use, since many research weights are non-commercial.

**Running well on old phones**

| Constraint | Design answer |
| --- | --- |
| 2 to 4 GB RAM, slow chip | No on-device ML is required. Frame selection uses simple sharpness checks. |
| Weak GPU | Three viewer tiers chosen automatically: full 3D, lite 3D (low-poly, no shadows), and a 2D top-down plan with product cards that always works |
| Slow or metered data | Small uploads, compressed 3D assets loaded on demand, designs cached for offline viewing |
| Small storage | Keep the install small; download room and product assets only when needed |
| Old OS versions | Support as far back as the app framework allows; confirm the exact minimum Android and iOS versions when the framework is chosen |

One India-specific shortcut: flats in the same tower share layouts. Scan each flat type once, store it, and every neighbour skips the scan with exact dimensions.
