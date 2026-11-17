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

1. **My home.** The app opens here. Before the first room: one before and after, one line and one button, "Add a room". After that: a card per room (hero still, name, last updated, number of designs) and "Add a room". Scanning is reached only from "Add a room". Guest session starts silently.
2. **Capture.** No room-type picker: scan whatever you want redone, a whole room, one corner or the balcony. The camera fills the screen with one thin progress ring and one plain instruction at a time ("Move slowly around the room", "Get the corners"). Coverage ticks softly under your fingers as it grows, and Done appears inside the ring when there is enough. A nudge shows only when something needs fixing (too dark, too fast, glare); the scan pauses softly, keeps everything so far, and you can keep going anyway. The scan is the technology, not the product: the mesh, guardrail chips, compass map and live labels are diagnostics, shown only with the debug flag in development and preview builds.
3. **Review.** Before anything is uploaded: how much of the room is in, what is still missing in plain words ("The side behind you", "The floor"), and a rough size when the scan saw two pairs of facing walls. Two ways on: "Rescan this part", which carries on the same scan and points at the missing part, or "Looks good", which starts the upload. The scan mesh shows here for a moment, as a "we got your room" glimpse.
4. **Space Profile.** "We found a living room": the detected space type and size, with a Change action, drawn over your photo with the error band. "What should we redo?" offers "All of it" or "Just a part" (draw around a corner or wall). Drag a door, mark each existing item keep, replace or remove, optionally add tape values (each snaps in with a haptic tick and re-fits the space).
5. **Taste.** Age band and household (two taps), 8 to 12 adaptive swipes, optional references, budget slider with "strict" or "can stretch 10%", must-haves and banned colours, "consider Vastu" toggle. Ends with your Taste Profile in plain words, editable.
6. **Sign in.** Asked only at "Design my room": Truecaller, Google, Apple, WhatsApp OTP fallback.
7. **Generating.** Three stages in plain words, each ticking off as it finishes: "Measuring your walls", "Finding your furniture", "Designing three looks". No bar that just ends: the last tick hands straight on to the reveal. Push when ready.
8. **Reveal.** First your room itself, in its hero views; then three swipeable designs (Best value, Best match, Bold), each with the total cost read from its `Design`. Until the twin exports hero views and the design engine sends designs, the app shows sample content through the same interface, labelled as a sample.
9. **Room.** One screen per room with exactly three tabs. Room: the hero views (fixed viewpoints and short orbits, no free movement), the room's size with its source and error band, and a slot for the furnished floor plan. Designs: the three looks, "why this works", and a Vastu view that switches on only when the scan has a compass reading. Shopping list: the chosen look's products, each with price, buy link and fit status, and the design's total. The look and its list are views of one `Design`. No floor-plan import, no in-app checkout. Swap per item comes with the plan editor.
10. **Plan.** Dimensioned 2D plan; drag and rotate re-run the verifier live with haptic snaps.
11. **Shopping list.** Total, breakdown by category, cheaper alternative and rent option per item, grouped by retailer, buy links through our redirect.
12. **Share.** Before and after reel, 9:16, with a link that opens the design in the app, or the landing page for people without it (a web viewer comes after launch).
13. **Vastu.** No tab of its own. Vastu lives as the Vastu view on each room's Designs tab: direction, room scorecard and guidance for that room, on only with a compass reading; deeper help later.
14. **Saved designs and history.** Reached from each room on My home.

## The brief

The `Brief` combines the Taste Profile with per-space choices: budget and flexibility, intent (refresh, full makeover, rearrange only), must-haves, items to keep, Vastu preference. It is the only input the design engine reads besides the Space Profile and the catalog.
