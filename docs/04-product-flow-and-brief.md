# Product flow and brief

Every stage of the journey is one schema object, so the stages cannot drift apart.

| Stage | You receive | Object |
| --- | --- | --- |
| Input | Photos or video of any space, and optional measurements | `Capture` |
| Understanding | Space profile and constraints | `SpaceProfile` |
| Personalisation | Style, budget, preferences | `TasteProfile`, `Brief` |
| Design | Three proposed transformations | `Design` x3 |
| Visualisation | Redesigned room image | `Render` (from `Design`) |
| Spatial view | Layout with dimensions | `Plan` (from `Design`) |
| Commerce | Products and budget | `ShoppingList` (from `Design`) |
| Action | Save, share, shop | `Event` log |

## Screens

1. **Welcome.** Tagline, before and after loop, "Start with a room". Guest session starts silently.
2. **Capture.** No room-type picker: scan whatever you want redone, a whole room, one corner or the balcony. As you pan, a glowing mesh spreads over what the camera has mapped, built on the phone from real feature points with no AI and no server cost. Live chips watch light, speed and shake, level, and mirrors and glare; when one fails the scan pauses softly with a fix and keeps everything mapped so far. Gallery photos are allowed. Budget phones get dots and edges instead of the full mesh.
3. **Space Profile.** "We found a living room": the detected space type and size, with a Change action, drawn over your photo with the error band. "What should we redo?" offers "All of it" or "Just a part" (draw around a corner or wall). Drag a door, mark each existing item keep, replace or remove, optionally add tape values (each snaps in with a haptic tick and re-fits the space).
4. **Taste.** Age band and household (two taps), 8 to 12 adaptive swipes, optional references, budget slider with "strict" or "can stretch 10%", must-haves and banned colours, "consider Vastu" toggle. Ends with your Taste Profile in plain words, editable.
5. **Sign in.** Asked only at "Design my room": Truecaller, Google, Apple, WhatsApp OTP fallback.
6. **Generating.** Meaningful progress (plan drawing itself, palette forming), push when ready.
7. **Reveal.** Your photo dissolves into the redesigned room, lamps on; then three swipeable designs (Best value, Best match, Bold), each with total cost.
8. **Design detail.** Render, "why this works", plan tab, shopping list tab, Vastu points, swap per item.
9. **Plan.** Dimensioned 2D plan; drag and rotate re-run the verifier live with haptic snaps.
10. **Shopping list.** Total, breakdown by category, cheaper alternative and rent option per item, grouped by retailer, buy links through our redirect.
11. **Share.** Before and after reel, 9:16, with a link that opens the web viewer for people without the app.
12. **Vastu tab.** Direction, room scorecard, guidance; deeper help later.
13. **My rooms.** Saved rooms and designs, history.

## The brief

The `Brief` combines the Taste Profile with per-space choices: budget and flexibility, intent (refresh, full makeover, rearrange only), must-haves, items to keep, Vastu preference. It is the only input the design engine reads besides the Space Profile and the catalog.
