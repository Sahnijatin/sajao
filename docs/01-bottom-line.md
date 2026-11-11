# Bottom line

Build it as a measured room plus a rules-based layout solver plus a real product catalog, with the LLM used only as a thin translator. That one decision delivers accuracy, low cost and the self-improving loop together.

1. **Geometry is measured, never generated.** Any phone camera captures the room, a cloud model rebuilds its shape, and a tape measurement locks the scale. AR sensors and LiDAR speed this up when present but are never required. No image generator or LLM ever decides a dimension.
2. **Every item placed is a real, in-stock product with real dimensions.** The 3 variations are built from catalog SKUs, so what she sees is what she can buy, and it provably fits.
3. **Layout is solved, not imagined.** A constraint solver places items under hard rules (no collisions, door swing clear, walkways of 75 cm or more, budget cap). Hallucination is structurally impossible in this step.
4. **The LLM does two small jobs.** It turns the brief and chat messages into structured instructions. A small, cheap model does this for well under 1 rupee per design.
5. **Learning is a data flywheel, not a self-rewriting AI.** Every drag, swap, save, click and purchase becomes training data. Small ranking models retrain automatically each night and ship only if they beat the current version on a fixed test set.
6. **The catalog is the real moat and the real bottleneck.** Sourcing products with correct dimensions and usable 3D models is harder than the AI. Plan for it first.

Start with one room type (living room or bedroom), India, about 2,000 to 3,000 curated products, on any Android or iOS phone with a camera.
