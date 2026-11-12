# Reveal, editor and share reel

## The reveal: her room, redesigned

Real-time phone 3D alone looks like a game next to the rooms people save. So the hero result is her own photo, redesigned:

1. The scan knows exactly where her camera was for every kept frame.
2. The 3D design is rendered from that same camera, giving each item's exact position, outline and depth.
3. Existing furniture marked "remove" is masked out with SAM 3 and cleaned.
4. An image editing model paints the final photoreal image, guided by the depth and outlines and given the real product photos as references. Candidates: Qwen-Image-Edit-2509 (Apache 2.0, self-hosted, multi-image references, depth and edge guidance) or a hosted Gemini image model.
5. **Fidelity check:** each item is cut out of the render and compared with its product photo by embedding similarity. Drifted items are re-rendered or the 3D view is shown instead.

Label: "Illustrative render. Layout and sizes are exact." Renders are made for the design she opens, not all three up front.

## The 3D editor

- Native rendering with react-native-filament (physically based, far lighter than a web view on budget phones).
- Dollhouse and walk-through cameras. Items snap to walls and floor with a magnetic haptic, glow red on collision, show live distances in cm.
- Swap carousel: the next 10 alternatives that fit the same spot, pre-fetched.
- Lock and regenerate: the engine redesigns around locked items.
- Live budget total with a rolling counter.
- Paint and flooring previews on her photo using the wall and floor masks.
- **Day and night:** daylight dims, lamps glow warm, shadows soften. Lighting is the strongest mood change in every reference, so this is a core feature.
- Viewer tiers: full 3D, lite 3D (fewer lights, no soft shadows), 2D plan with product cards.

## Share reel

The empty-to-finished reveal is what people post. Sajao makes it for her:

- 3 to 4 of her own scan angles; for each, her real "before" frame cuts to the redesigned room from the identical camera angle.
- Lamps on in the "after", 6 to 10 seconds, 9:16, music, ready for Instagram and WhatsApp.
- A subtle Sajao end card. Every shared reel is an ad.

## Web viewer

Any design opens from a link in a browser as a lighter web build with the photo renders and a simple 3D view. It powers family votes and sharing.

## Later

AR view at true scale on supported phones; photoreal walk-throughs (Gaussian splats) for high-end phones once performance on mid-range devices is proven.
