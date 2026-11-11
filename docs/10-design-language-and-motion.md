# Design language, motion and wow moments

Reuse the LiveMap design system: bright frosted glass, soft layered shadows, one confident accent, and spring motion. In this app the room is the hero, so the interface stays neutral and lets her space carry the colour.

**Tokens carried over from LiveMap**

| Element | Value in LiveMap | Use here |
| --- | --- | --- |
| Background | Soft grey-white #eef0f5 with faint colour blobs | App canvas behind cards and sheets |
| Text | Near-black #1d1d1f, two greys for secondary text | Same |
| Glass | White at 62% with 20 to 24 px blur and 180% saturation | Camera overlay chips, bottom sheets, floating toolbars over the 3D view |
| Shadows | Three stacked soft shadows | Cards, lifted furniture, product tiles |
| Accent | Blue #0a7cff, with tinted 10% fills | Primary actions, selection, the verified badge |
| Type | SF Pro on Apple, Geist elsewhere | SF Pro on iOS, Geist bundled on Android |
| Movement curve | cubic-bezier(.32, .72, 0, 1) at 0.45 s | Screen and sheet transitions |
| Selection spring | Stiffness 380, damping 32 | Toggles, chips, item selection |
| Layout glide | Critically damped, 0.45 s | Lists and panels resizing |
| Reduced motion | Every animation becomes an instant change | Same, on both platforms |

A dark theme already exists in the LiveMap tokens and can ship later. AR and camera screens should always use the glass-on-camera style regardless of theme.

**Wow moments, in the order she meets them**

| Moment | What she sees and feels | Low-end fallback |
| --- | --- | --- |
| Scan painting | As she turns, a soft glow paints over the parts of the room already captured. The ring fills; each corner lands with a haptic tap. | Ring and corner dots only |
| The plan draws itself | While the cloud works, her floor plan is drawn line by line and measurements tick in. No spinner anywhere. | Same, it is 2D |
| Tape lock | An animated tape stretches along the wall to measure. When she confirms, every dimension snaps into place with a tick and a "Verified" badge. | Same |
| Room rises | Walls lift from the plan one by one and the camera eases into a dollhouse orbit. | Cross-fade to the lite view |
| Design reveal | Furniture drops in piece by piece with a soft spring and settling shadows. Three designs sit as swipeable cards with depth. | Staggered fade-in |
| Before and after | A divider she drags between her real photo and the new design. | Same |
| Living drag | A lifted item gets a deeper shadow, snaps to walls with a magnetic haptic, glows red on collision, and shows live distances in cm. | Snap and distances, no shadow |
| Swap | The old item melts into the new one; the price counter rolls to the new total. | Cross-fade |
| Paint flood | Tap a wall and colour sweeps across it like a roller. | Instant colour change |
| Day to night | One switch dims the daylight, lamps glow warm and shadows soften. The strongest "ambience" moment. | Two pre-set lighting states |
| Step into AR | The 3D view glides to her real camera view and the furniture stays in place. | Hidden on unsupported phones |
| Share reel | A 6-second before-and-after clip generated for WhatsApp and Instagram. | Still image card |

**How to build it on both platforms**

- **One brand, platform manners.** The look is identical on iOS and Android. Behaviour follows each platform: back gesture and system navigation on Android, swipe-back and sheet detents on iOS.
- **Motion stack.** React Native Reanimated and Gesture Handler for 60 fps gestures off the main thread, Skia for glass, glows and paint effects, Rive or Lottie for the coach animations, three.js for the room.
- **Haptics are part of the design.** Light tick for corner captured, medium for snap, success pattern for verified. Android haptics vary by phone, so keep to simple patterns there.
- **Blur is expensive on old Android.** Detect the device tier at launch. Low tier gets a solid translucent tint instead of live blur, fewer shadows and shorter animations. It should still look intentional, not broken.
- **Motion has a job.** Every animation shows where something came from or confirms an action. Keep most under 0.45 s. Only the room rise and design reveal are allowed to be longer, and both are skippable with a tap.
- **Fun without clutter.** Small rewards at real milestones: scan complete, room verified, under budget. No confetti on every tap.
- **Performance budget.** 60 fps on a mid-range phone, 30 fps minimum on the lite tier, and first screen visible in under 2 seconds.
