# Space Twin risk spike

Internal feasibility testing for the Space Twin risks (Notion SJ-116). Runs on
public datasets only, never used for training and never shipped. The report with
results, images and the recommendation is in
[`eval/twin-risk/REPORT.md`](../../../eval/twin-risk/REPORT.md).

## What it tests

1. **Objects.** Segment every object across frames, lift to 3D boxes, name them,
   and compare with ARKitScenes annotated boxes (recall, size error, position
   error), with LiDAR depth and without it (MapAnything depth from images,
   intrinsics and AR poses). Two detectors are compared (Grounding DINO base and
   YOLOE-26x), both with SAM 2.1 masks.
2. **Splats.** Train a Gaussian splat per scene, split it by object masks, hide
   one object, and compare two fills: (A) inpainting the shell planes behind it
   in texture space, (B) inpainting every frame then fine-tuning the splat.
3. **Phones.** Compressed on-device splats versus server-rendered views: file
   sizes, quality lost, render time, bitrate and GPU cost.
4. **Register.** Every model, library and dataset is listed in
   `docs/24-third-party-register.md`. Choices are made on quality, speed and cost.

Every model runs as a local GPU job on Modal; no hosted model API is called.
Boxes come from code fitted to measured or estimated points; no generative model
sets a dimension.

## Layout

| Path | What |
| --- | --- |
| `src/twin_risk/` | Pure Python, tested in CI: poses, upright boxes, 3D IoU, matching and metrics, voxel fusion, split vote rule, costs |
| `tests/` | Tests for the pure parts |
| `gpu/app.py` | Modal app: images, volume, one function per stage |
| `gpu/twin_gpu/` | GPU and CPU jobs: dataset prep, objects, splat training, split and fills, phone measurements, LaMa wrapper |

## Data

| Dataset | Scenes | Used for |
| --- | --- | --- |
| ARKitScenes (validation) | 47331265, 41159541, 41159566 (living rooms), 47430034, 47895350 (bedrooms) | Phone video frames (640x480), ARKit poses, LiDAR depth (high confidence only), annotated 3D boxes |
| Replica | frl_apartment_0, apartment_1 | Photoreal quality; rendered by ray casting the mesh colours on CPU |
| Mip-NeRF 360 | room, kitchen, counter | Photoreal quality on real photos, COLMAP poses (no metric scale) |

## Pinned versions

| Component | Version |
| --- | --- |
| Modal client | 1.6.4 with the `api-proxy-support` extra (needed behind an HTTP proxy) |
| CUDA base image | `nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04`, Python 3.11 |
| PyTorch, torchvision | 2.4.1, 0.19.1 (cu124) |
| gsplat | 1.5.3, built from source for compute 7.5, 8.6, 8.9 |
| Transformers | 4.57.1 (Grounding DINO base, SAM 2.1 Hiera Large) |
| Ultralytics | 8.4.214 (YOLOE-26x-seg, text prompts) |
| MapAnything | commit `3d10cf7a`, checkpoint `facebook/map-anything` |
| LaMa | big-lama TorchScript from simple-lama-inpainting v0.1.0 |
| Open3D, trimesh, pycolmap, OpenCV | 0.19.0, 4.5.3, 3.10.0, 4.10.0.84 |
| splat-transform | 3.11.2 (Node 22) |

## Rerun

```bash
pip install 'modal[api-proxy-support]==1.6.4'   # MODAL_TOKEN_ID and MODAL_TOKEN_SECRET set
cd <repo root>
modal run services/spikes/twin-risk/gpu/app.py --stage smoke     # image check
modal run services/spikes/twin-risk/gpu/app.py --stage prep      # download and convert (CPU)
modal run services/spikes/twin-risk/gpu/app.py --stage objects   # masks; ARKitScenes boxes and scores
modal run services/spikes/twin-risk/gpu/app.py --stage splat     # train splats
modal run services/spikes/twin-risk/gpu/app.py --stage edit      # split, hide, fill A and B
modal run services/spikes/twin-risk/gpu/app.py --stage phone     # variants, compression, timings
python services/spikes/twin-risk/gpu/collect.py                   # copy results and images to eval/twin-risk/
```

Add `--scenes room,kitchen` to run a subset. Outputs live on the Modal volume
`sajao-twin-risk` under `out/<scene>/`.

Tests for the pure parts run with the rest of the repo: `uv run pytest services/spikes`.
