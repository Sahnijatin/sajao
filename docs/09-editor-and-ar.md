# Reveal, editor and share reel

## Staged reveal

GPU workers that scale to zero take time to load large models, and design passes take time too. So results arrive in stages instead of promising a fixed time:

1. **Plan and 3D designs** from the CPU engine as soon as they pass the verifier.
2. **Photo render** of the design she opens, when the GPU worker finishes.

Times are measured in phase 0 and beta; no time claim appears in the app or marketing until measured.

## Photo render: her room, redesigned

1. The design is rendered in 3D from the camera position of one of her scan frames, using each product's 3D model at its exact place and size.
2. Items marked "remove" are masked with SAM 3 and cleaned.
3. An image model **harmonizes** the composite (lighting, shadows, materials) at low strength, guided by depth and outlines, with product photos as references. Candidates: Qwen-Image-Edit-2509 (Apache 2.0, self-hosted) or a hosted Gemini image model.
4. **Checks per item:**
   - Outline check: the item's outline in the render must overlap its projected 3D outline (target 85% or more). This catches moved or resized items.
   - Likeness check: embedding similarity to the product photo.
5. A failed item triggers a retry at lower strength; a second failure shows the 3D render instead.

Label: **"Illustrative render. Exact layout and sizes in the 3D view."** Fine details such as leg shapes may differ in the render; the 3D view and the product page are the reference.

## The 3D editor

- react-native-filament: native physically based rendering, light on budget phones.
- Dollhouse and walk-through cameras. Snap to walls with a magnetic haptic, red glow on collision, live distances in cm.
- Swap carousel of alternatives that fit the same spot, pre-fetched.
- Lock and regenerate.
- Live budget with a rolling counter.
- Paint and flooring previews on her photo using surface masks.
- Day and night lighting.
- v1: one 3D tier plus a 2D plan fallback chosen by device tier. More tiers in the Next tier.

## Share reel (v1, simple)

- 3 to 4 of her scan angles; each cuts from her real "before" frame to the redesigned room rendered from the same camera.
- Lamps on, 6 to 10 seconds, 9:16, music, Sajao end card.

## Next and later

Web viewer for shared links (Next). AR view and photoreal walk-throughs (Later).
