# Vastu

Vastu guidance is offered as close to correct as a phone allows, labelled honestly: "Vastu guidance, as close as possible. For a full consultation, speak to an expert." The rule set is drafted from published sources and reviewed by an expert consultant before launch.

## Direction (v1)

Phone compasses inside concrete buildings can be off by tens of degrees, so a compass reading alone is never trusted:

1. **Compass during the scan,** logged and averaged across the walk, with a calibration prompt when unstable.
2. **Building outline** from open building datasets (Google Open Buildings covers India). Room walls usually run parallel to the building's outer walls, so the outline gives the angle; the compass only picks which side is north. (unvalidated: measured on the golden set)
3. **One-tap confirmation** on a map: "Your main door faces roughly East?"

If the outline is missing or the sources disagree, direction is marked approximate and only guidance mode is available.

## Room-level Vastu (v1)

Bed head direction and placement; heavy furniture toward the south-west; TV wall, seating direction and entrance clearance; desk facing; mirror placement, colour guidance, plant and water element placement.

| Mode | Behaviour |
| --- | --- |
| Off | No Vastu influence |
| Guidance | Adds to the soft score; designs show which points they meet |
| Strict | Key rules become hard constraints (only when direction is confirmed) |

## Whole-home Vastu (Next tier)

16-zone analysis from a photo of the builder's floor plan read by a vision model, or the room marked on a 3 by 3 grid. Gives each room's zone, the centre of the home and the entrance direction.

## Testing

Expert-approved test rooms run in the fast CI tier. Orientation error is measured on the golden set.

## Later

Live sessions with a Vastu expert, booked in the app.
