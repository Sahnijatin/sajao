# Space Twin risk spike: report

Internal feasibility test on public datasets. It answers three questions before the Space Twin epic commits to a design: can we find and measure the furniture in a scanned room, can we hide an object in a splat and fill the hole believably, and can budget phones show the result. Every number below comes from `results/`; `tables.md` has the full tables and `images/` the before and after images. Code and rerun steps are in `services/spikes/twin-risk/`.

## Go or no-go

Scored on two ARKitScenes living rooms (`arkit_living_47331265`, `arkit_living_41159541`) and one Replica scene (`apartment_1`), as agreed. The other seven scenes are supporting evidence.

| Risk | Verdict | Why |
| --- | --- | --- |
| Objects: find, name and size the furniture | Go, with tape for anything that decides fit | 67 to 70% of the visible annotated objects found with the right class (IoU 0.25), 80 to 100% at loose overlap; centre error 13 to 24 cm; size error 13 to 27%. Good enough to place, label and suggest; not good enough to decide fit without tape. |
| Splats: photoreal room | Go | 26.0 and 25.7 dB held-out PSNR on the ARKit rooms after pose and exposure refinement (17 and 18 dB without it), 37.5 dB on Replica; 5 to 10 min on one L40S. |
| Hide an object and fill the hole | Go for small objects, conditional for large ones | Per-frame inpainting then a short re-train (fill B) covers 99 to 100% of the hole and removes the object cleanly when the background was seen. Large objects against walls no camera saw come out soft; the capture flow has to ask for those views. |
| Budget phones | See "Phones" below | |

## 1. Objects

Pipeline: detector on every frame (Grounding DINO base or YOLOE-26x, household vocabulary), SAM 2.1 masks from the boxes, masks lifted to 3D with depth (LiDAR or MapAnything, which estimates metric depth from images and AR poses), fused into instances, then code fits an upright box to each instance. The model never sets a dimension: depth gives points, code fits the box. Scored against the ARKitScenes 3D boxes with 3D IoU.

Go or no-go rooms, objects in view, raw AR poses:

| Room | Detector | Depth | Found, right class (IoU 0.25) | Found, loose (IoU 0.05) | Centre error | Size error |
| --- | --- | --- | --- | --- | --- | --- |
| living 47331265 (10 objects) | Grounding DINO | LiDAR | 70% | 80% | 24 cm | 22% |
| | YOLOE | LiDAR | 70% | 90% | 15 cm | 27% |
| | Grounding DINO | MapAnything | 70% | 80% | 20 cm | 18% |
| living 41159541 (9 objects) | Grounding DINO | LiDAR | 56% | 67% | 13 cm | 13% |
| | YOLOE | LiDAR | 67% | 100% | 15 cm | 22% |
| | Grounding DINO | MapAnything | 56% | 67% | 22 cm | 20% |

Across all five ARKit rooms (38 objects in view): Grounding DINO with LiDAR 66% (71% loose), 13 cm, 13% size error; YOLOE with LiDAR 71% (89% loose), 15 cm, 22%; MapAnything instead of LiDAR 61 to 63%, 18 to 20 cm. Over all 80 annotated objects, including those the video barely saw, recall falls to 41 to 46%: coverage, not the models, is the limit.

Findings:

- YOLOE finds more (89% loose) and runs about 8x faster (6 s versus 50 s for 270 frames); Grounding DINO gives tighter sizes. Recommendation: YOLOE for detection, SAM 2.1 for masks, and a class check with Grounding DINO only where YOLOE is unsure.
- LiDAR beats image-only depth by about 5 cm of centre error. Without LiDAR the result is still usable for placement, so Android phones without a depth sensor are not blocked, but every fit decision needs a tape value.
- Precision is low (14 to 32%) because the vocabulary also finds small items the ground truth does not annotate. This needs a size and class filter before the user sees a list.
- Pose refinement from the splat does not improve objects; raw AR poses are enough.

## 2. Splats and object removal

Splat: gsplat 1.5.3, 15,000 steps, with per-camera pose and per-image exposure refinement for phone captures. Without refinement the ARKit rooms reach only 17 to 18 dB because AR poses drift by about 2 to 4 cm and 0.6 to 1 degree.

| Room | Gaussians | Train time (L40S) | PSNR, raw poses | PSNR, refined |
| --- | --- | --- | --- | --- |
| living 47331265 | 2.58 M | 8.0 min | 16.9 dB | 26.0 dB |
| living 41159541 | 1.91 M | 6.3 min | 18.3 dB | 25.7 dB |
| apartment_1 (Replica) | 1.10 M | 4.0 min | n/a | 37.5 dB |

Split: each Gaussian takes the label most of the object masks give it. Mask IoU of the split against the 2D masks on held-out views is 0.52 to 0.69 per scene (0.20 to 0.94 per object). The removal also clears Gaussians inside the object's box and a margin around it, so the split does not need to be perfect.

Two fills compared:

| | Fill A: inpaint the shell planes | Fill B: inpaint every frame, re-train |
| --- | --- | --- |
| How | Fit floor and wall planes (RANSAC, snapped level or vertical), render each plane's texture, inpaint it with LaMa, add flat Gaussians | LaMa on every training frame with the object mask, then 5,000 fine-tune steps |
| Time per object | 0 to 7 s | 1.7 to 4.4 min on L40S (about 0.06 to 0.15 USD) |
| Hole covered | 69 to 100% | 99 to 100% |
| Result | Visibly wrong: misplaced texture, floating panels, or no change where no plane is found | Plausible; clean for small objects; soft and smeared where the background was never seen |

Decision: fill B. Fill A is only a fast preview. Images: `images/<scene>/edit/<kind>/` show photo, object hidden, fill A and fill B side by side.

## 3. Phones

PHONE_SECTION

## 4. Cost per room

Measured GPU time for the production path on one L40S (0.000542 USD per second):

| Step | Time | Cost |
| --- | --- | --- |
| Splat with pose refinement | 4.5 to 10 min | 0.15 to 0.33 USD |
| Objects (YOLOE, SAM 2.1, lift, fuse) | 0.5 to 1.5 min | 0.01 to 0.04 USD |
| Hide one object (fill B) | 1.7 to 4.4 min | 0.06 to 0.15 USD |
| Compress for phones (CPU) | about 1 to 4 min | under 0.01 USD |

A room with three removed objects costs about 0.35 to 0.80 USD of GPU time. The whole spike across ten scenes recorded 5.20 USD of stage time; the true spend, including image builds and idle containers, was higher but within the free credits.

## Recommendation

1. Build the Space Twin on Gaussian splats trained on the server with pose and exposure refinement. Without refinement phone captures are not good enough.
2. Objects: YOLOE plus SAM 2.1 lifted with LiDAR where the phone has it and MapAnything where it does not. Code fits the boxes; every dimension carries the error band measured here (about 15 cm and 20%), and tape decides fit.
3. Object removal: per-frame inpainting plus a short re-train (fill B). The capture flow must ask the user to film behind large furniture; without those views the fill is soft.
4. Phones: see the phone recommendation above.
5. Follow-ups for the epic: phone fps on a real iPhone and a budget Android; a size and class filter for detected objects; a coverage check during capture; SAM 3 (weights are gated, not tested here).

## Limitations

- Feasibility only: 10 public scenes, of which 3 decide. ARKitScenes ground truth covers 17 furniture classes; small items are not annotated.
- Mip-NeRF 360 scenes are not metric, so they count only for splat and edit quality.
- The `room` edit images were made before plane snapping; `kitchen` has no edit run. Three ARKit rooms have no edit run (budget).
- Phone render speed is measured on server GPUs and scaled; it is not a device measurement.

## Licenses

Every model, library and dataset used is in `docs/24-third-party-register.md` with its stated license. Two need the legal review before any product use: the MapAnything checkpoint is CC BY-NC 4.0, and ARKitScenes and Replica are research datasets. YOLOE and Ultralytics CLIP are AGPL-3.0, allowed under the current policy.
