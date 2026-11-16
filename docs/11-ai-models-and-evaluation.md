# AI models and evaluation

AI decides taste and appearance; geometry and code decide fit. Every model output passes a measurable check before you see it.

## Models

| Job | Model | License | Tier |
| --- | --- | --- | --- |
| Camera poses, point cloud, planes (multi-view) | MapAnything (Apache 2.0 release) or VGGT commercial checkpoint | Apache 2.0; commercial checkpoint | Must |
| Single-image metric geometry | MoGe-2 | To confirm before use | Must |
| Surface and item segmentation | SAM 3 | SAM license (commercial use allowed) | Must |
| Item naming, light direction, catalog vision scoring | Vision-language model via gateway | Provider terms | Must |
| Brief to spec, AI designer, product extraction | Language models via gateway | Provider terms | Must |
| Guided render | Winner of the render bake-off (primary) and cheaper runner-up (fallback) | Provider terms | Must |
| Aesthetic judge, likeness and structure checks | Vision model plus embedding similarity | Provider terms; permissive | Must |
| Taste and product embeddings | Open image-text embedding model (SigLIP 2 class) | Permissive, to confirm | Must |
| Upload safety classifier | Off-the-shelf classifier | To confirm | Must |
| Image to 3D for hero products | TRELLIS.2, SAM 3D Objects | MIT; SAM license | Next |
| Live object labels during the scan (on device) | EfficientDet-Lite0 on COCO classes, run with MediaPipe Tasks | Apache 2.0 (model and MediaPipe) | Must |
| Floor plan reading, design chat | Vision and language models | Provider terms | Next |
| Taste ranker, compatibility model | Small models trained by us | Ours | Later |

Every model and dataset is listed in the third-party register (`docs/24-third-party-register.md`); the legal team reviews it separately. Prompts and model versions are pinned in the repo.

## Space Twin risk spike

The twin risk spike (`services/spikes/twin-risk/`, report in `eval/twin-risk/`) compares candidates on public datasets and picks on quality, speed and cost. Every model, library and dataset it uses is listed in the third-party register.

## Indian-home detector dataset

The on-device detector knows COCO classes, not Indian home objects. `services/dataset` builds a labelled set of real Indian rooms in six stages: find YouTube home tours, screen them with Gemini for room segments, download only kept segments, sample frames without near-duplicates or blur, auto-label behind the model gateway with a hand-checked sample, and version the result on Modal storage. Licenses are recorded per source; the set is for internal training only. Its first use is the Indian-object test set for the twin's detector (below). Property listing photos are added only after the YouTube pilot report.

## Object detection for the twin

The twin finds objects on the server with an open-vocabulary detector, prompted with a pinned list of general and Indian home object names (diwan, puja unit, jhoola, almirah, shoe rack, gas stove, floor seating and others). YOLOE is the default. The detector sits behind a swappable interface, and Grounding DINO and OWLv2 (both Apache-2.0) are benchmarked on the same Indian-object test set, so the twin can switch within a day if the legal review declines YOLOE. A fine-tuned Indian-home detector is trained only if the default misses the recall bar on that test set. A first benchmark on openly licensed web photos, before the scan test set exists, is in `eval/twin-indian/REPORT.md`: OWLv2 found 83% of the Indian objects, Grounding DINO 48% and YOLOE 9%. The detector order is one setting (`SAJAO_DETECTORS`).

## Render bake-off

Real rooms run through Gemini 3 Pro Image, Gemini 3.1 Flash Image, Seedream, FLUX.2 and Qwen-Image-Edit with the same guide and product references, scored blind on excitement, product fidelity and structure. The winner becomes the primary; the cheaper runner-up becomes the fallback in the gateway. The bake-off reruns whenever a candidate model changes.

## Golden set

About 25 real Indian rooms to start (photos, a short video and tape values), growing over time and weighted toward typical flats. It is the ground truth for geometry error bands, render checks, design feasibility and cost per room. Tracked in the Notion "Golden set" database.

## Evaluation tiers

| Tier | Runs | Contents | Blocks merge? |
| --- | --- | --- | --- |
| Fast | Every commit, in CI | Schema round trips, solver and verifier property tests, relaxation order, fixed-room design tests, Vastu rule cases, gateway fallback tests | Yes |
| Nightly | Scheduled | Geometry accuracy on the golden set, render checks, cost per room | No; regressions are reviewed |
| Release | Before each store build | Blind votes, catalog audit, device matrix run | Yes, for the release |

Nightly and release measurements are compared with confidence intervals, not single numbers.

## Not doing

Generating whole rooms from a text prompt; training our own reconstruction or image model; fine-tuning a large language model before real usage data exists.

## Learning from users (Later)

Swaps, drags, saves, buy taps and skipped designs update the taste profile immediately and, later, train a taste ranker through a gated pipeline (candidate, evaluation, shadow, small traffic share, promote or roll back). Hard rules and the verifier never change from learning.
