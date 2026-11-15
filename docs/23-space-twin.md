# Space Twin

Every scan becomes a full 3D digital twin of the space: the room itself and every object in it, each as its own editable item. People rearrange, remove, replace and redesign on the twin, and the render, the plan and the shopping list are all derived from it.

## Why this is new

| What exists | What it lacks |
| --- | --- |
| Floor-plan scanners (boxes for furniture) | Need a depth sensor; objects are grey boxes, not your objects |
| Photoreal 3D capture apps | One frozen scene; nothing can be moved or removed |
| Photo-based "place a product" tools | No real room geometry; one retailer; no fit checks |
| Design apps | Rooms and furniture drawn by hand |

The problem we solve: **any phone, one scan, every object separated, measured, recreated and matched to real products**, with fit verified.

## Layers of the twin

| Layer | Holds | Source |
| --- | --- | --- |
| Capture | Keyframes with camera poses and intrinsics, AR planes, depth and LiDAR scene mesh where present, live detections, sensor log, video | Phone; immutable once uploaded |
| Shell | Walls, floor, ceiling, doors, windows as editable planes, each with a projected photo texture (objects masked out), material guesses (paint colour, tile size) | AR data plus feed-forward reconstruction; scale cross-checked against anchors |
| Objects | One record per item: class, name, oriented 3D box with size and error band, masks and best crops from several views, 3D model, splat subset, catalog matches, state (keep, move, remove, replace) | Open-vocabulary segmentation tracked across frames, lifted to 3D; named by a vision-language model |
| Appearance | Per-object 3D model at true size; photoreal room splat split by object | Image-to-3D from the object's own crops; Gaussian splat trained on keyframes |
| Identity | Closest catalog product and same-size replacements per object | Image and text embeddings plus size filter |

## Edits are deltas

The capture never changes. A design is a twin version plus an ordered list of edits: move, rotate, remove, replace (with a SKU), add (a SKU at a pose), restyle surface (paint, flooring). The solver and verifier check every edit; the render, plan, 3D view and shopping list read the same twin plus deltas. Undo is dropping a delta.

## Pipeline

1. **On the phone:** AR session where available (pose tracking, planes, LiDAR mesh with surface classes), live on-device detector with labels pinned in 3D, guardrails, coverage. Without AR: video and frames only.
2. **Upload:** one capture package, resumable and idempotent.
3. **Geometry (GPU):** refine poses and build a metric point cloud; fit the shell; cross-check scale.
4. **Objects (GPU):** segment every object across frames, merge into instances, lift to 3D boxes, name them.
5. **Room Profile ready:** the shell and object list come back first, so the user can confirm and edit quickly.
6. **Lazily, when needed:** per-object 3D models, catalog matches, the splat split by object, fills behind removed objects. Each step is a durable job, cached by content hash.

## Viewing

- **2D plan:** shell plus object footprints, always available.
- **Hero render:** guided image edit of the user's photo, now guided by twin edits.
- **3D twin view:** splat room plus object models plus swapped products; orbit and walk. Budget phones get textured meshes or a server-rendered fly-through.

## Honesty rules (unchanged)

Every dimension keeps a value, a source and an error band. Generated 3D models never set an object's size; the measured box does. Renders and 3D views are labelled illustrative. Fit claims only when the margin covers the band.

## Model and license rules

Every model and library in this pipeline needs a recorded commercial license before use. No AGPL components (for example, Ultralytics YOLO). Candidates to evaluate: feed-forward reconstruction (MapAnything Apache 2.0 release, VGGT commercial checkpoint), segmentation (SAM 3), image to 3D (SAM 3D Objects, TRELLIS.2), splat training and rendering (gsplat, Apache 2.0), on-device detection (EfficientDet-Lite class, Apache 2.0).

## Risks to retire first

1. Splitting a splat cleanly by object and filling what was behind a removed object.
2. Rendering splats on phones at 30 fps, including mid-range Android.
3. GPU cost per room once splats and per-object models are added; everything after the Room Profile runs lazily.
4. Object recall and size accuracy in cluttered Indian rooms, measured on the golden set.
