# No-AR poses: can the twin be built without AR tracking?

Phones without ARCore have no tracked camera poses. This benchmark asks whether feed-forward poses from the video, with metric depth from MoGe-3, are close enough to AR poses to build the same twin. If they are, the "AR required" rule could go; if they fail on scale only, a one-tap tape value could fix it. Every number comes from `results/`; the code is in `services/spikes/twin-noar/`.

## Setup

- **Rooms:** the five ARKitScenes rooms from SJ-116 (three living rooms, two bedrooms). AR poses are withheld from the method under test and used only as the reference.
- **Poses:** MapAnything `facebook/map-anything-apache` (Apache 2.0, pinned revision), fed 120 frames per room with images and intrinsics only; and VGGT-1B-Commercial (VGGT License v1, pinned revision), fed the same 120 images alone. VGGT's results are in their own section below.
- **Depth:** MoGe-3 ViT-L (MIT) per frame.
- **Scale, each source in turn:** the pose model's own scale; MoGe-3 depth; and the true scale taken from the AR camera path (the best a tape value could do).
- **Row 1, objects:** the same YOLOE masks, lifting, fusion and box fitting as the worker, scored against the ARKitScenes boxes on objects the video saw. Bedroom 47430034 has no annotated objects in view, so objects are scored on four rooms (38 objects). Pass bar: recall at IoU 0.25 within 5 points of AR poses, and centre error within 5 cm.
- **Row 2, splat:** the worker's splat trainer (gsplat 1.5.3, 15k steps, with its pose and exposure refinement), trained once on AR poses with LiDAR depth and once on predicted poses with MoGe-3 depth. Score: PSNR on every 8th frame, held out. Pass bar: within 1 dB of AR poses.

## Results

### Row 1: objects (four rooms, 38 objects)

| Poses and scale | Recall, right class (IoU 0.25) | Median centre error |
| --- | --- | --- |
| AR poses (reference) | 55% | 17 cm |
| MapAnything, own scale | 24% | 31 cm |
| MapAnything, MoGe-3 scale | 29% | 34 cm |
| MapAnything, true scale | 26% | 27 cm |

Per room:

| Room | AR recall, centre | Pose error (centre RMSE, rotation) | Scale error, own / MoGe-3 | Recall at own / MoGe-3 / true scale |
| --- | --- | --- | --- | --- |
| Living 41159541 | 67%, 19 cm | 26 cm, 2.6° | −2% / +9% | 67% / 78% / 56% |
| Living 41159566 | 67%, 9 cm | 55 cm, 7.1° | +11% / +16% | 22% / 22% / 33% |
| Living 47331265 | 50%, 15 cm | 54 cm, 3.9° | −12% / +8% | 10% / 20% / 20% |
| Bedroom 47895350 | 40%, 25 cm | 137 cm, 6.6° | +71% / +92% | 0% / 0% / 0% |
| Bedroom 47430034 | no objects in view | 86 cm, 8.1° | +44% / +24% | |

### Row 2: splat quality

| Room | AR poses | Predicted poses | Gap |
| --- | --- | --- | --- |
| Living 47331265 | 24.02 dB | 20.83 dB | −3.2 dB |
| Living 41159541 | 25.13 dB | 20.38 dB | −4.8 dB |
| Living 41159566 | 16.13 dB | 13.54 dB | −2.6 dB |
| Bedroom 47430034 | 20.20 dB | 15.82 dB | −4.4 dB |
| Bedroom 47895350 | 18.90 dB | 15.35 dB | −3.6 dB |
| Mean | 20.88 dB | 17.18 dB | −3.7 dB |

## Verdict: fails, and not on scale alone

- **Row 1 fails** in three of four rooms. Giving the method the true scale does not close the gap (26% against 55%), so a tape value cannot fix it.
- **Row 2 fails** in every room, by 2.6 to 4.8 dB. The splat trainer refines poses, but it cannot recover errors of 25 cm to 1.4 m.
- **The cause is the poses themselves.** Over 120 frames of a walk around a room, the feed-forward poses drift by 26 cm to 1.4 m and 2.6° to 8°. The one room with a small pose error (living 41159541: 26 cm, 2.6°) passes row 1, which supports this reading. Scale errors are real too (−12% to +92%), but they are the smaller problem.

So the review's "fails on scale only" case does not apply: a one-tap tape step would not make no-AR phones good enough. The "AR required for the twin" rule (decision A) stands. Phones without ARCore keep the "Use photos" flow.

## VGGT-1B-Commercial

The same harness, rooms, frames and pass bars, with VGGT poses in place of MapAnything's.

### Row 1: objects (four rooms, 38 objects)

| Poses and scale | Recall, right class (IoU 0.25) | Pose error (centre RMSE, rotation) |
| --- | --- | --- |
| AR poses (reference) | 55% | |
| VGGT, MoGe-3 scale | 45% | 10 to 29 cm, 1.6 to 3.8 degrees |
| VGGT, true scale | 47% | 10 to 28 cm |
| VGGT, own scale | 3% | its scale is not metric (61 to 72% too small) |

Per room, at MoGe-3 scale (recall and median centre error, AR in brackets): living 47331265 40%, 25 cm (50%, 15 cm); living 41159541 67%, 23 cm (67%, 19 cm); living 41159566 56%, 20 cm (67%, 9 cm); bedroom 47895350 20%, 32 cm (40%, 25 cm). MoGe-3 scale was within -14% to 0% of the true scale in every room.

### Row 2: splat quality

| Room | AR poses | VGGT poses | Gap |
| --- | --- | --- | --- |
| Living 47331265 | 24.02 dB | 23.77 dB | -0.3 dB |
| Living 41159541 | 25.13 dB | 23.46 dB | -1.7 dB |
| Living 41159566 | 16.13 dB | 15.02 dB | -1.1 dB |
| Bedroom 47430034 | 20.20 dB | 18.57 dB | -1.6 dB |
| Bedroom 47895350 | 18.90 dB | 18.08 dB | -0.8 dB |
| Mean | 20.88 dB | 18.98 dB | -1.9 dB |

### Verdict for VGGT: much closer, still short of the bars

- **Row 1 fails narrowly**: 10 points of recall below AR (bar: 5) and 4 to 11 cm more centre error (bar: 5 cm). True scale barely helps (47%), so the remaining gap is pose error, not scale.
- **Row 2 fails on average** (-1.9 dB; bar: 1 dB) but passes in two of five rooms.
- **Scale is solved by MoGe-3** for VGGT poses (within 14%), unlike MapAnything (up to 92% off).
- VGGT inference took about 12 s per room of 120 frames on an L40S.

Founder decision: AR stays required for the twin at launch. Two post-launch tasks are in Notion: a no-AR twin via VGGT with wider error bands and a required tape step, and VGGT as a health check on AR poses.

## Limits

- Two pose models. Other feed-forward models were not tried.
- Five rooms; living 41159566 splats poorly even with AR poses (16 dB), so its gap carries less weight.
- MapAnything saw 120 frames, not every frame. More frames may reduce drift but cost more GPU time.
- A splat-refined-pose variant of row 1 was planned and not run; given row 2's gaps, refinement does not recover these errors.

## Cost

MapAnything: 3.94 USD of GPU time on Modal (L40S), within its 5 USD budget: about 0.1 USD for poses and depth, the rest for the ten splat runs. VGGT: about 1.9 USD (poses, scoring and five splat runs; the AR-pose splats were reused), within its 4 USD budget.
