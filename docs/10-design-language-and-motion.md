# Design language, motion and haptics

Sajao uses the LiveMap design system: bright frosted glass, soft layered shadows, one confident accent, and spring motion. The room is the hero, so the interface stays neutral and lets your space carry the colour. Minimal, modern, sleek, and calm.

## Tokens carried over from LiveMap

| Token | Value | Use in Sajao |
| --- | --- | --- |
| Canvas | #eef0f5 with slow drifting colour blobs (blue, pink, amber) | Home, brief, list screens |
| Ink | #1d1d1f; secondary #55595f and #636873 | Text |
| Glass | White at 62%, 28 px blur, 180% saturation, hairline border | Camera overlays, sheets, floating toolbars over 3D |
| Shadows | Three stacked soft shadows | Cards, lifted furniture, product tiles |
| Accent | #0a7cff with 10% tints | Primary actions, selection, Verified badge |
| Status | Green #1fae55, red #ff3b30, orange #ff8a00 | Scan guides, collisions, warnings |
| Radius | 20 px panes, 14 px cards | Same |
| Type | SF Pro on iOS, Geist bundled on Android | Same |
| Ease | cubic-bezier(.32, .72, 0, 1), 0.45 s | Screen and sheet transitions |
| Selection spring | Stiffness 380, damping 32 | Chips, toggles, item selection |
| Layout glide | Critically damped, 0.45 s | Lists and panels resizing |
| Dark theme | LiveMap dark tokens | Later; camera screens always use glass on camera |

On mobile the tokens live in one theme package. Springs use Reanimated with the same constants; glass uses native blur or Skia; effects (glows, grid, paint sweep) use Skia.

## Haptics

| Moment | iOS | Android |
| --- | --- | --- |
| Corner captured | Light tick | Short tick |
| Level reached (line turns green) | Selection tick | Short tick |
| Room verified | Success pattern | Double tick |
| Furniture snaps to a wall | Medium impact | Short tick |
| Collision | Rigid bump | Single strong tick |
| Swap lands | Soft impact | Short tick |
| Price counter rolls | Soft ticks | None |
| Design reveal | Light cascade as items land | Single tick |

Android motors vary widely, so patterns stay simple there. Haptics respect system settings.

## Wow moments, in order

| Moment | What you see | Low-end fallback |
| --- | --- | --- |
| Scan mesh | A glowing mesh spreads over what the camera has mapped, with a white sweep at its edge; corners tick | Dots and edges |
| Tape lock | An animated tape stretches along the wall; dimensions snap in; Verified | Same |
| Plan draws itself | Floor plan drawn line by line, measurements tick in | Same |
| Room rises | Walls lift from the plan; camera eases into a dollhouse orbit | Cross-fade |
| Design reveal | Your photo dissolves into the redesigned room, lamps glowing | Cross-fade |
| Living drag | Lifted item, deeper shadow, magnetic snap, live cm | Snap and distances |
| Swap | Old item melts into the new; price rolls | Cross-fade |
| Paint sweep | Colour sweeps across the wall like a roller | Instant change |
| Day to night | Daylight dims, lamps glow warm | Two preset states |
| Share reel | Before cuts to after from the same angle | Still card |

## Rules

- One brand, platform manners: Android back gesture, iOS swipe-back and sheet detents.
- Motion has a job: it shows where something came from or confirms an action. Most under 0.45 s; room rise and reveal may be longer and are skippable.
- Device tier detected at launch. Low tier: tinted glass instead of live blur, fewer shadows, shorter animations. Still intentional, never broken.
- Reduced motion turns every animation into an instant change.
- Performance: 60 fps on mid-range phones, 30 fps minimum on the lite tier, first screen under 2 seconds.
- Small rewards at real milestones only. No confetti on every tap.
