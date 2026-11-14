# Product flow and brief

Every stage of the journey is one schema object, so the stages cannot drift apart.

| Stage | You receive | Object |
| --- | --- | --- |
| Input | Room photos and optional measurements | `Capture` |
| Understanding | Room profile and constraints | `RoomProfile` |
| Personalisation | Style, budget, preferences | `TasteProfile`, `Brief` |
| Design | Three proposed transformations | `Design` x3 |
| Visualisation | Redesigned room image | `Render` (from `Design`) |
| Spatial view | Layout with dimensions | `Plan` (from `Design`) |
| Commerce | Products and budget | `ShoppingList` (from `Design`) |
| Action | Save, share, shop | `Event` log |

## Screens

1. **Welcome.** Tagline, before and after loop, "Start with a room". Guest session starts silently.
2. **Room type.** Living room or bedroom at launch.
3. **Capture.** Camera with glass guides (level line, "step back", "include a corner", "turn on lights"), coverage ring, on-device sharpness checks. Video or 3 to 8 photos; gallery upload allowed.
4. **Room Profile.** The plan drawn over your photo with size and error band. Drag a door, mark each existing item keep, replace or remove, optionally add tape values (each snaps in with a haptic tick and re-fits the room).
5. **Taste.** Age band and household (two taps), 8 to 12 adaptive swipes, optional references, budget slider with "strict" or "can stretch 10%", must-haves and banned colours, "consider Vastu" toggle. Ends with your Taste Profile in plain words, editable.
6. **Sign in.** Asked only at "Design my room": Truecaller, Google, Apple, WhatsApp OTP fallback.
7. **Generating.** Meaningful progress (plan drawing itself, palette forming), push when ready.
8. **Reveal.** Your photo dissolves into the redesigned room, lamps on; then three swipeable designs (Best value, Best match, Bold), each with total cost.
9. **Design detail.** Render, "why this works", plan tab, shopping list tab, Vastu points, swap per item.
10. **Plan.** Dimensioned 2D plan; drag and rotate re-run the verifier live with haptic snaps.
11. **Shopping list.** Total, breakdown by category, cheaper alternative and rent option per item, grouped by retailer, buy links through our redirect.
12. **Share.** Before and after reel, 9:16, with a link that opens the web viewer for people without the app.
13. **Vastu tab.** Direction, room scorecard, guidance; deeper help later.
14. **My rooms.** Saved rooms and designs, history.

## The brief

The `Brief` combines the Taste Profile with per-room choices: budget and flexibility, intent (refresh, full makeover, rearrange only), must-haves, items to keep, Vastu preference. It is the only input the design engine reads besides the Room Profile and the catalog.
