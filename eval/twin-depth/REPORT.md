# No-LiDAR depth: commercial models versus MapAnything

Phones without a depth sensor (most Android phones) need depth from images to lift detected objects into 3D. The SJ-116 spike used MapAnything, whose checkpoint is CC BY-NC 4.0 and cannot ship. This benchmark asks which commercially licensed model replaces it, and how far each is from LiDAR. Every number comes from `results/`; the code is in `services/spikes/twin-depth/`.

## Setup

- **Rooms:** the five ARKitScenes rooms from SJ-116 (three living rooms, two bedrooms), 270 frames each, raw ARKit poses. LiDAR depth (high-confidence pixels only) is ground truth.
- **Models**, each with its own pinned revision:

| Model | License | Kind |
| --- | --- | --- |
| MapAnything `facebook/map-anything` | CC BY-NC 4.0 | Multi-view, takes AR poses and intrinsics (the baseline) |
| MapAnything `facebook/map-anything-apache` | Apache 2.0 | Same code and inputs, commercial weights |
| Depth Anything 3 Metric Large | Apache 2.0 | One image; metres = focal × output / 300 |
| MoGe-3 ViT-L | MIT | One image, given the field of view from the AR intrinsics |

- **Depth score:** AbsRel and δ < 1.25 against LiDAR, median scale ratio (1.00 is perfect metric scale), share of LiDAR pixels covered.
- **Object score:** the spike's YOLOE masks lifted with each depth through the same fusion and box fitting, then compared with the ARKitScenes boxes (3D IoU), on objects the video saw. Bedroom 47430034 has no annotated objects in view, so objects are scored on four rooms (37 objects); depth on all five. Code fits every box; no model sets a dimension.

## Results

| Depth | Recall, right class (IoU 0.25) | Loose (IoU 0.05) | Centre error | Size error | AbsRel | δ < 1.25 | Scale ratio | GPU time per room (L40S) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LiDAR | 71% | 90% | 14 cm | 21% | | | | |
| MapAnything, CC BY-NC | 61% | 85% | 17 cm | 19% | 0.100 | 0.93 | 1.07 | 86 s |
| MapAnything, Apache 2.0 | 51% | 72% | 21 cm | 21% | 0.114 | 0.86 | 0.93 | 80 s |
| Depth Anything 3 Metric | 64% | 77% | 20 cm | 19% | 0.085 | 0.93 | 0.98 | 8 s |
| **MoGe-3 ViT-L** | **64%** | **90%** | **17 cm** | **19%** | **0.074** | **0.95** | **0.99** | 79 s |

Per room (recall, centre error):

| Room | LiDAR | MapAnything NC | MapAnything Apache | DA3 Metric | MoGe-3 |
| --- | --- | --- | --- | --- | --- |
| living 47331265 | 70%, 15 cm | 50%, 18 cm | 30%, 26 cm | 70%, 18 cm | 60%, 20 cm |
| living 41159541 | 67%, 15 cm | 67%, 22 cm | 56%, 24 cm | 67%, 33 cm | 67%, 21 cm |
| living 41159566 | 78%, 7 cm | 67%, 14 cm | 78%, 12 cm | 78%, 8 cm | 78%, 8 cm |
| bedroom 47895350 | 70%, 18 cm | 60%, 15 cm | 40%, 20 cm | 40%, 21 cm | 50%, 19 cm |

Findings:

- **MoGe-3 replaces MapAnything with no loss.** It matches or beats the CC BY-NC baseline on every measure: best depth (AbsRel 0.074, δ 0.95), metric scale within 1%, the same loose recall as LiDAR (90%) and the same centre error as MapAnything (17 cm).
- **The Apache MapAnything weights are clearly worse** than the CC BY-NC ones (51% versus 61% recall, 21 versus 17 cm) and scale 7% short. Not a drop-in replacement.
- **Depth Anything 3 Metric is ten times faster** (8 s per room) with good depth and scale, but its object placement varies by room (33 cm centre error in living 41159541). Good as a fallback.
- **Gap to LiDAR** with MoGe-3: recall 64% versus 71%, centre error 17 versus 14 cm. Same conclusion as the spike: usable to place, label and suggest; fit decisions still need tape.
- Small samples: 9 or 10 objects per room, so one object moves recall by about 10 points. The ranking is consistent across the depth metrics, which use every LiDAR pixel.

## Recommendation

1. **Primary for the no-LiDAR path: MoGe-3 ViT-L (MIT).** Fallback: Depth Anything 3 Metric Large (Apache 2.0), a different model family, so one failure does not take out both.
2. **MapAnything is not in the shipped chain.** The CC BY-NC checkpoint cannot be used commercially, and the Apache checkpoint loses to both alternatives.
3. Error band for image-only depth in the twin: about 17 cm centre and 19% size (LiDAR: 14 cm, 21%). Tape decides fit either way.

## GPU spend

Billed by Modal for the app `sajao-twin-depth-eval`, including failed starts: see the PR. Steady-state cost per room for the recommended model is 79 s of L40S, about 0.04 USD.

## Licenses

All four checkpoints and both code repositories are in `docs/24-third-party-register.md`.
