# Render, plan and share

The hero image is a guided edit of your own photo, steered by the plan and the exact product photos, then checked. Free generation from a text prompt is never used.

## Render pipeline

1. **Clean.** Items marked remove or replace are masked and erased.
2. **Guide.** The solver's layout is projected into the photo's camera as per-item footprints, depth and outlines.
3. **Generate.** A multi-reference image model receives the cleaned photo, the guide and the product photos. More than about 6 products means two passes: big pieces first, then decor. Paint and flooring change in the same pass using the wall and floor masks.
4. **Check.** Structure preserved outside the edit zones; each product found inside its footprint (grounding) and similar to its SKU photo (likeness); no extra invented furniture; aesthetic judge score above threshold.
5. **Retry or fall back.** One retry with tighter guidance, then a clean 3D render of the same design. Never a broken image.

Three designs render at 1K on the cheaper image model; the design you open upgrades to 2K on the premium model. The primary and fallback models are chosen by the render bake-off (see [AI models and evaluation](11-ai-models-and-evaluation.md)).

## Reveal

Your photo dissolves into the redesigned room with lamps on, then the three designs as swipeable cards, each with total cost on the card. Every render carries the "Illustrative render" label.

## Spatial view

- **2D plan (Must).** Drawn with Skia: room outline, items to scale, clearances in feet and inches, door swings, and the error band as a soft halo when unverified. Drag and rotate re-run the verifier live with haptic snaps.
- **Swap.** A carousel of alternatives per item, pre-filtered to fit the same footprint and budget.
- **3D dollhouse (Next).** react-native-filament on capable phones, 2D fallback on low-tier phones.

## Share reel

Before to after from the same angle, 6 to 10 seconds, 9:16, Sajao end card. Built on the server so it works on every phone. The share link opens the design in the app, or the landing page for people without it; a web viewer comes after launch.
