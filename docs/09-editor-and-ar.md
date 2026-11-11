# Live 3D editor and AR view

Render the room in real-time 3D on the phone, not as generated images. That is what makes drag, rotate and swap instant, free to serve, and geometrically honest.

- **Editor view.** Her room rebuilt as a textured 3D shell, with a dollhouse view and a walk-through view. Items snap to walls and floor, collisions glow red, the budget total updates as she swaps.
- **Swap carousel.** Tapping an item shows the next 10 alternatives that fit the same spot. They are pre-fetched, so swapping needs no server call.
- **Lock and regenerate.** She locks what she likes and the solver redesigns around it.
- **AR mode.** Standing in the real room, she sees the items at true scale through the camera (ARKit, ARCore). This is the trust moment before buying.
- **Day and night toggle.** Scene lighting changes with the chosen lamps and bulb warmth, which is how "ambience" is shown.
- **Photoreal render, optional.** A cloud render of the final design, conditioned on the 3D scene's depth so geometry cannot drift. Labelled "illustrative". This is the only step with real per-use cost, so it is a paid or rate-limited feature.

Recommended build: a React Native app, plain camera capture on every phone with optional native boosters (Swift for ARKit and RoomPlan, Kotlin for ARCore), and one three.js editor shared by the app and the web. The shared web editor means any design opens from a link in a browser, which powers sharing. Unity with AR Foundation is the alternative: one engine for everything, but a heavier app and a harder fit for normal app screens.
