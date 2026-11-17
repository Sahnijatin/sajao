# Design language, motion and haptics

Sajao looks like a warm contemporary Indian home: ivory walls, sand and warm wood, soft daylight. The structure comes from the LiveMap design system (frosted glass, soft layered shadows, one accent, spring motion); the palette is warm. The room is the hero, so the interface stays quiet, with generous whitespace, and lets your space carry the colour. Premium and calm.

## Tokens

| Token | Value | Use in Sajao |
| --- | --- | --- |
| Canvas | Warm ivory #f6f1e8 with slow drifting warm blobs (terracotta, amber, wood); surfaces #fffdf9 | Home, brief, list screens |
| Ink | Warm near-black #221e19; secondary #5a5249 and #6b6258 | Text |
| Neutrals | Sand #e9dfd0, wood #b08968, daylight #fbf4e4 | Image placeholders and tracks; small marks; highlights. Never text |
| Glass | Light: white at 62%, 28 px blur, 180% saturation, hairline border. Dark: near-black at 42%, 28 px blur, 160% saturation, white text | Light over the canvas and photos, on sheets and floating toolbars; dark on camera screens |
| Shadows | Three stacked soft shadows | Cards, lifted furniture, product tiles |
| Accent | Terracotta #ad4f27 with 10% tints; white text on it passes 4.5:1 | Primary actions, selection, Verified badge |
| Status | Green #1fae55, red #ff3b30, orange #ff8a00 | Scan guides, collisions, warnings |
| Radius | 20 px panes, 20 px cards, 30 px sheet corners; buttons and chips fully rounded | Same |
| Type | Instrument Serif headlines, bundled on both platforms; body in SF Pro on iOS and bundled Geist on Android | Same |
| Buttons | 56 px pills; 32 px small pills | Primary actions; inline actions |
| Ease | cubic-bezier(.32, .72, 0, 1), 0.45 s | Screen and sheet transitions |
| Selection spring | Stiffness 380, damping 32 | Chips, toggles, item selection |
| Layout glide | Critically damped, 0.45 s | Lists and panels resizing |
| Dark theme | A warm dark set | Later; camera screens always use glass on camera |

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
