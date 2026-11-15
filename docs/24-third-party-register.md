# Third-party register

Every model, library and dataset used to build, train or evaluate Sajao is listed here for the legal team, who review it separately. Engineering adds a row when something is first used; review never blocks engineering.

| Name | Type | Used for | Source | License as stated by the source | Training use | Added by task |
| --- | --- | --- | --- | --- | --- | --- |
| Expo, React Native, Supabase and coding guideline skills | Agent skills | Development guidance | See `.claude/skills/THIRD_PARTY_NOTICES.md` | MIT | No | Repo agent setup |
| gsplat 1.5.3 | Library | Gaussian splat training and rendering (twin appearance) | https://github.com/nerfstudio-project/gsplat | Apache 2.0 | No | SJ-116 twin risk spike |
| PyTorch 2.4.1 and torchvision 0.19.1 | Library | GPU runtime for all spike models | https://github.com/pytorch/pytorch | BSD 3-clause | No | SJ-116 twin risk spike |
| Grounding DINO base (IDEA-Research) | Model | Open-vocabulary object detection and naming | https://huggingface.co/IDEA-Research/grounding-dino-base | Apache 2.0 | No | SJ-116 twin risk spike |
| YOLOE-26x-seg (Ultralytics 8.4.214) | Model and library | Open-vocabulary object detection and naming, compared with Grounding DINO | https://github.com/ultralytics/ultralytics | AGPL-3.0 (Ultralytics also sells an enterprise license) | No | SJ-116 twin risk spike |
| Ultralytics CLIP | Library | Text tokenizer for YOLOE class prompts | https://github.com/ultralytics/CLIP | AGPL-3.0 | No | SJ-116 twin risk spike |
| MobileCLIP2 text encoder (Apple) | Model | Text embeddings for YOLOE class prompts (downloaded by Ultralytics) | https://huggingface.co/apple/MobileCLIP2-B | Apple ML Research Model Terms of Use (apple-amlr); code MIT | No | SJ-116 twin risk spike |
| SAM 2.1 Hiera Large (Meta) | Model | Object masks from detector boxes | https://huggingface.co/facebook/sam2.1-hiera-large | Apache 2.0 | No | SJ-116 twin risk spike |
| MapAnything (Meta), code at commit 3d10cf7a | Library | Metric multi-view geometry | https://github.com/facebookresearch/map-anything | Apache 2.0 | No | SJ-116 twin risk spike |
| MapAnything checkpoint `facebook/map-anything` | Model | Metric depth without LiDAR from images, intrinsics and AR poses | https://huggingface.co/facebook/map-anything | CC BY-NC 4.0 (an Apache 2.0 checkpoint, `facebook/map-anything-apache`, also exists) | No | SJ-116 twin risk spike |
| LaMa big-lama | Model | AI inpainting of plane textures and of frames | https://github.com/advimman/lama | Apache 2.0 | No | SJ-116 twin risk spike |
| simple-lama-inpainting v0.1.0 TorchScript export | Model file | Packaged big-lama weights loaded by the spike | https://github.com/enesmsahin/simple-lama-inpainting | Apache 2.0 | No | SJ-116 twin risk spike |
| Transformers 4.57.1 (Hugging Face) | Library | Loading Grounding DINO and SAM 2.1 | https://github.com/huggingface/transformers | Apache 2.0 | No | SJ-116 twin risk spike |
| OpenCV 4.10 (headless) | Library | Image processing | https://github.com/opencv/opencv | Apache 2.0 | No | SJ-116 twin risk spike |
| Open3D 0.19 | Library | Ray casting Replica meshes | https://github.com/isl-org/Open3D | MIT | No | SJ-116 twin risk spike |
| trimesh 4.5.3 | Library | Mesh loading and light mesh export | https://github.com/mikedh/trimesh | MIT | No | SJ-116 twin risk spike |
| pycolmap 3.10 | Library | Reading Mip-NeRF 360 COLMAP poses | https://github.com/colmap/pycolmap | BSD 3-clause | No | SJ-116 twin risk spike |
| pytorch-msssim 1.0 | Library | SSIM loss and metric | https://github.com/VainF/pytorch-msssim | MIT | No | SJ-116 twin risk spike |
| NumPy, Pillow | Library | Arrays and images | https://numpy.org, https://python-pillow.org | BSD 3-clause; MIT-CMU | No | SJ-116 twin risk spike |
| FFmpeg (Ubuntu 22.04 package) | Tool | Encoding server-rendered video (H.264) | https://ffmpeg.org | LGPL 2.1 or later; this distribution build enables GPL parts (GPL 2 or later) | No | SJ-116 twin risk spike |
| PlayCanvas splat-transform 3.11.2 | Tool | Compressing splats (SOG, compressed PLY, SPZ) | https://github.com/playcanvas/splat-transform | MIT | No | SJ-116 twin risk spike |
| Node.js 22 | Runtime | Runs splat-transform | https://nodejs.org | MIT | No | SJ-116 twin risk spike |
| NVIDIA CUDA 12.4.1 cuDNN devel image | Container image | GPU base image for spike jobs | https://hub.docker.com/r/nvidia/cuda | NVIDIA Deep Learning Container License and CUDA EULA | No | SJ-116 twin risk spike |
| Modal client 1.6.4 | Library and service | Running GPU and CPU jobs | https://github.com/modal-labs/modal-client | Apache 2.0 (client); service under Modal terms | No | SJ-116 twin risk spike |
| ARKitScenes (Apple), validation scenes 47331265, 41159541, 41159566, 47430034, 47895350 | Dataset | Phone video frames, ARKit poses, LiDAR depth and annotated 3D boxes as ground truth | https://github.com/apple/ARKitScenes | ARKitScenes license file: non-commercial grant, plus a commercial grant for licensees under 700 million monthly active users | No | SJ-116 twin risk spike |
| Replica (Meta), frl_apartment_0 and apartment_1 | Dataset | Photoreal apartment scenes for splat quality | https://github.com/facebookresearch/Replica-Dataset | Replica Dataset Research Terms: non-commercial research or educational use | No | SJ-116 twin risk spike |
| Mip-NeRF 360 (Google), room, kitchen, counter | Dataset | Real indoor photos with COLMAP poses for splat quality | https://jonbarron.info/mipnerf360/ | No license stated on the source page | No | SJ-116 twin risk spike |
