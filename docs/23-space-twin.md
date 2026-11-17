# Space Twin

Every scan becomes a full 3D digital twin of the space: the room itself and every object in it, each as its own editable item. People rearrange, remove, replace and redesign on the twin, and the render, the plan and the shopping list are all derived from it.

## Status at launch

The full twin is the direction, not the launch. At launch the twin supplies what the redesign needs: the capture package, the measured shell (walls, floor, ceiling, doors and windows with error bands), the object inventory with boxes, and hero views with a safe viewing region. The redesign is shown on those hero photos, with a measured plan and a shopping list.

After launch: the room splat and its viewer on the phone, 3D models of your own items, catalog matches for your own items, removal inside the splat, and rearrange-only mode. What the evidence showed: the splat reads like a soft photo near the capture path and breaks down away from it; removing an object inside the splat leaves a visible ghost at room scale, so removal for redesigns is 2D inpainting on hero keyframes; and frame rate on a budget phone has not been measured on a device. The sections below describe the full twin and stay as the design for that work.

## What the design engine and the render read

Added to the twin by the room understanding step, all from the fused geometry and the hero photos:

- **Footprint** of every object and built-in: its box seen from above, with width and depth as dimensions (value, source, error band), and whether it stands on the floor (a clock or a ceiling fan does not).
- **Keep or replace** for every object. The rule keeps fixtures (fans, lights, AC units, switchboards, geysers) and lets everything else be replaced; the person can change it, and their choice is kept.
- **Hero masks**: for every object, its mask in each hero photo where at least 30% of it is in frame and not hidden behind something nearer. The detector's own mask is reused where it has one for that keyframe; otherwise the segmenter is prompted with the object's box projected into the photo. Masks are not dilated; the render decides how far to grow them before inpainting.
- **Free floor**: the floor area less the footprints of everything kept that stands on the floor (objects marked keep, and built-ins), with an error band from the walls' and footprints' bands.

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
| Objects | One record per item: class, name, oriented 3D box with size and error band, masks and best crops from several views, 3D model, splat subset, catalog matches, state (keep, move, remove, replace) | Open-vocabulary detection (YOLOE by default, prompted with general and Indian home object names, behind a swappable interface) and segmentation tracked across frames, lifted to 3D; named by a vision-language model |
| Appearance | Per-object 3D model at true size; photoreal room splat of the room as scanned | Image-to-3D from the object's own crops; Gaussian splat trained on keyframes |
| Viewing | Six to ten hero views (real keyframe poses) and the safe region the camera may stand in | Code: coverage from depth, sharpness from the image, positions from the capture path |
| Identity | Closest catalog product and same-size replacements per object | Image and text embeddings plus size filter |

## Edits are deltas

The capture never changes. A design is a twin version plus an ordered list of edits: move, rotate, remove, replace (with a SKU), add (a SKU at a pose), restyle surface (paint, flooring). The solver and verifier check every edit; the render, plan, 3D view and shopping list read the same twin plus deltas. Undo is dropping a delta.

## Pipeline

1. **On the phone:** AR session where available (pose tracking, planes, LiDAR mesh with surface classes), live on-device detector with labels pinned in 3D, guardrails, coverage. Without AR: video and frames only.
2. **Upload:** one capture package, resumable and idempotent.
3. **Geometry (GPU):** refine poses and build a metric point cloud; fit the shell; cross-check scale.
4. **Objects (GPU):** segment every object across frames, merge into instances, lift to 3D boxes, name them.
5. **Room Profile ready:** the shell and object list come back first, so the user can confirm and edit quickly.
6. **Lazily, when needed:** per-object 3D models, catalog matches, the room splat with its hero views. Each step is a durable job, cached by content hash.

## Viewing

- **2D plan:** shell plus object footprints, always available.
- **Hero render:** guided image edit of a hero keyframe (the user's own photo, with its pose), guided by twin edits. Removing furniture for a redesign happens here, as 2D inpainting on the hero keyframes.
- **3D twin view:** the room splat as scanned, the "before". It is shown only from the hero views, small orbits around them, and camera positions inside the safe region. Budget phones get a server-rendered fly-through along the same path.

## Where the twin can be shown from

The splat is sharp where the phone stood and falls apart away from it: views from the middle of a room the phone only walked around are not usable, and streaks appear a short step off the path. So every twin carries its own viewing limits (`viewing` in the `SpaceTwin` schema), and the viewer and the reveal use nothing else.

- **Hero views:** six to ten real keyframe poses, best first. Code picks them: each adds the most of the room not yet shown (10 cm cells from depth, counted from the floor to 1.8 m, so ceiling earns nothing), weighted towards level views across the room, among the sharp keyframes, and no two are near duplicates. A photo whose horizon is more than 10 degrees off level is not picked while enough level ones exist. A hero view is always a real keyframe, so its photo and its pose are exact. Hero views do not depend on the splat: a twin without one still names them.
- **Orbit:** around a hero view the camera may move up to 30 cm and turn up to 15 degrees.
- **Safe region:** the camera may stand within 30 cm of a keyframe position. `insideSafeRegion` and `clampToSafeRegion` in `@sajao/schemas/twin` are the check the viewer uses.

The 30 cm radius is a starting value from review: renders 20 to 50 cm off the path already showed streaks. It moves only when held-out views that far from a training camera score close to views beside one.

The splat is the "before" twin only. It is not edited: removing an object inside the splat left a ghost silhouette and smeared walls in review. Redesigns start from the hero keyframes, which the render work inpaints in 2D.

## Honesty rules (unchanged)

Every dimension keeps a value, a source and an error band. Generated 3D models never set an object's size; the measured box does. Renders and 3D views are labelled illustrative. Fit claims only when the margin covers the band.

## Model and license rules

Engineering uses whatever gives the best result, including public datasets for training and evaluation. Every model, library and dataset goes into the third-party register (`docs/24-third-party-register.md`) with its source and license; the legal team reviews it separately. Candidates to evaluate: feed-forward reconstruction (MapAnything Apache 2.0 release, VGGT commercial checkpoint), segmentation (SAM 3), image to 3D (SAM 3D Objects, TRELLIS.2), splat training and rendering (gsplat, Apache 2.0), on-device detection (EfficientDet-Lite class, Apache 2.0).

## Risks to retire first

1. Splat quality away from the capture path: floaters, streaks and blur. Measured per golden room near and far from the path; contained by hero views and the safe region; reduced by better capture coverage.
2. Rendering splats on phones at 30 fps, including mid-range Android.
3. GPU cost per room once splats and per-object models are added; everything after the Room Profile runs lazily.
4. Object recall and size accuracy in cluttered Indian rooms, measured on the golden set.
