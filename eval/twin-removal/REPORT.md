# Object removal: LaMa versus a diffusion inpainting model

Fill B hides an object in the twin: inpaint the object out of every training frame, then fine-tune the object-free splat on those frames (SJ-116). This compares the inpainting model inside fill B: LaMa (the spike's choice) against Qwen-Image, a recent diffusion model with an inpainting pipeline. Every number comes from `results/`; the code is in `services/spikes/twin-removal/`.

## Setup

- **Cases:** the large object (a sofa) and the small object (an armchair) in two ARKitScenes living rooms, the same objects the spike hid, picked with the spike's own rule and settings.
- **Same inputs for both models:** the hole in each training frame is where the removed Gaussians render. At most 48 frames that see the hole are inpainted by each model (the same frames); frames that see the hole but were not inpainted are left out of the fine-tune. "LaMa, all frames" is the spike's setting, as a reference.
- **Models:**

| Model | License | Settings |
| --- | --- | --- |
| LaMa big-lama | Apache 2.0 | Whole frame, as in the spike |
| Qwen-Image with the 8-step Lightning LoRA | Apache 2.0 (both) | Square crop around the hole at about 1 MP, pasted back inside the hole with a soft edge; prompt asks for the floor and wall to continue |
| Qwen-Image, full (ablation) | Apache 2.0 | 40 steps, guidance 4, negative prompt against furniture and objects |

- **Scores:**
  - **Known truth:** the same hole shape moved onto background the camera saw, so the fill is compared with real pixels (PSNR inside the hole, LPIPS on the hole's box). 12 to 20 holes per case.
  - **Fill agreement:** PSNR inside the hole between the fine-tuned splat and the model's own fills. Low means the fills disagree from view to view, which the splat turns into blotches.
  - **Ghost:** a detector's score for the removed class inside the hole on held-out views (lower is better, but see below).

## Results

| Case | Model | Known truth PSNR | LPIPS | Fill agreement | Ghost |
| --- | --- | --- | --- | --- | --- |
| living 47331265, sofa | LaMa | **24.2 dB** | **0.15** | **26.8 dB** | 0.25 |
| | Qwen-Image | 11.5 dB | 0.50 | 16.6 dB | 0.18 |
| | Qwen-Image, full | 13.6 dB | 0.40 | | |
| living 47331265, armchair | LaMa | **21.0 dB** | **0.16** | **25.9 dB** | 0.46 |
| | Qwen-Image | 11.9 dB | 0.43 | 15.9 dB | 0.47 |
| living 41159541, sofa | LaMa | **19.4 dB** | **0.17** | **29.7 dB** | 0.30 |
| | Qwen-Image | 10.6 dB | 0.35 | 19.7 dB | 0.47 |
| | Qwen-Image, full | 12.3 dB | 0.32 | | |
| living 41159541, armchair | LaMa | **18.1 dB** | **0.22** | **23.1 dB** | 0.43 |
| | Qwen-Image | 8.3 dB | 0.57 | 16.9 dB | 0.27 |

Time and cost per object: LaMa inpaints 33 to 44 frames in 1 to 5 s; Qwen-Image takes about 2.1 s per frame on an H100 (70 to 100 s per object, plus 40 s to load). The splat fine-tune is the same for both (3.4 to 4.4 min on an L40S).

Images: `images/<room>_<kind>_view<n>_strip.jpg` show photo, object hidden, LaMa, Qwen-Image and LaMa on all frames on held-out views. `images/known_truth_47331265_small.jpg` shows known-truth holes: real pixels, LaMa, Qwen-Image.

Findings:

- **LaMa wins on every measure against real pixels**, by 9 to 13 dB of PSNR and 2 to 3 times lower LPIPS, in all four cases.
- **Qwen-Image invents objects.** Given a furniture-shaped hole it paints furniture-like shapes (a cushion on a tabletop, a box against a wall), even with a prompt for empty floor and wall. Full guidance with a negative prompt helps only slightly (about 2 dB).
- **Its fills disagree across views** (10 dB lower agreement), so the splat averages them into blotchy patches. LaMa's fills are plain but consistent.
- **The ghost score favours Qwen-Image in two cases only because it destroys structure** in the hole; the images show a noisier result, not a cleaner removal.
- **Large objects remain the weak case for both**: where the background behind a sofa was never filmed, LaMa gives a smooth, sofa-coloured smear. More views behind large objects (the capture guidance task) is the fix, not a different inpainting model.

## Decision

- **Fill B keeps LaMa** (Apache 2.0) as the inpainting model; Qwen-Image is not kept.
- The removal step's fallback is the degraded path, not a second model: when LaMa or the fine-tune fails, the object stays visible with an honest message and the fill retries, rather than showing a worse fill.
- Capture guidance behind large objects stays on the plan; it is what will improve large removals.

## GPU spend

Billed by Modal for the app `sajao-twin-removal-eval`, including image builds and failed starts: see the PR.

## Licenses

Qwen-Image, the Lightning LoRA, diffusers and the other new libraries are in `docs/24-third-party-register.md`.
