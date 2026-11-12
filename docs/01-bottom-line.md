# Principles and scope

These decisions hold everything else together. A change that breaks one of them needs a decision log entry with a reason first.

## How to read these docs

They describe intended design, not working software. Anything marked **(unvalidated)** is a hypothesis for phase 0. When building, implement only what is inside the current tier of the cut line below, and build it deeply.

## Principles

1. **Geometry is measured, never generated.** Room dimensions come from her tape. The scan proposes shape, openings and items; she confirms. No language or image model ever decides a dimension or a position.
2. **AI decides taste and appearance; code decides fit.** An AI designer chooses the program, pairings and products. A solver places them. An independent verifier re-checks every hard rule.
3. **Always an honest result.** If a room cannot fit what she asked for, she is told what does fit and why. A design that fails the verifier is never shown.
4. **Every item is real and curated.** In stock, verified dimensions, matched to a style profile, with a working affiliate route and permission to use its images.
5. **The reveal is the product.** 3D first, then her photo redesigned, then a shareable before and after reel.
6. **Light app, heavy server.** The phone captures and displays; heavy models run in the cloud.
7. **Check everything AI produces.** Schema checks for text, geometry checks for layouts, outline and similarity checks for images.
8. **Honest by design.** Error bands shown, renders labelled illustrative, Vastu labelled guidance.
9. **Never stop suddenly.** When a model or provider fails or a cost cap is reached, the app degrades to a simpler path instead of failing.
10. **Learning from users comes in v2.**

## Cut line

| Tier | Scope |
| --- | --- |
| **Must (v1 launch)** | Scan plus tape measurement on any phone; living room and bedroom; curated catalog of a few hundred items; AI designer plus solver plus verifier with the relaxation order; 3D editor plus 2D plan fallback; photo render when a design is opened; buy list with affiliate links; room-level Vastu; simple share reel; event logging; model gateway with fallbacks; invite-based launch |
| **Next** | Whole-home Vastu from a floor plan photo; chat; web viewer; photo mode for the weakest phones; the three self-trained taste models; multiple 3D viewer tiers; entitlements (switched off) |
| **Later** | AR view; reconstruction-only measuring (if phase 0 proves it); photoreal walk-throughs; service leads; flat-type library; v2 learning |

## v1 scope facts

- India, consumer app, Android and iOS, any phone with a camera.
- Categories: lighting, paint and wall finishes, flooring and rugs, curtains, seating, beds, tables, storage, wall art, decor, plants.
- Free at launch, through invites. No paywall appears anywhere in the app.
