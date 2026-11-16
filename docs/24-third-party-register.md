# Third-party register

Every model, library and dataset used to build, train or evaluate Sajao is listed here for the legal team, who review it separately. Engineering adds a row when something is first used; review never blocks engineering.

| Name | Type | Used for | Source | License as stated by the source | Training use | Added by task |
| --- | --- | --- | --- | --- | --- | --- |
| Expo, React Native, Supabase and coding guideline skills | Agent skills | Development guidance | See `.claude/skills/THIRD_PARTY_NOTICES.md` | MIT | No | Repo agent setup |
| EfficientDet-Lite0 (int8, MediaPipe build) | Model | Live object labels during the AR scan, on the phone | https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector | Not stated on the MediaPipe model page; the same TensorFlow Hub model is listed as Apache-2.0 on its mirrors | No | SJ-33 AR-anchored scan |
| COCO 2017 | Dataset (indirect) | The detector's weights were trained on it by Google; Sajao does not train on it | https://cocodataset.org/#termsofuse | Annotations CC BY 4.0; images under the Flickr terms of use | No (not by Sajao) | SJ-33 AR-anchored scan |
| MediaPipe Tasks Vision 0.10.33 (iOS pod, Android library) | Library | Runs the on-device detector | https://github.com/google-ai-edge/mediapipe | Apache-2.0 | No | SJ-33 AR-anchored scan |
| ARCore SDK for Android 1.57.0 | Library | AR tracking, planes, depth and hit tests on Android | https://github.com/google-ar/arcore-android-sdk | Apache-2.0 for the SDK; Google APIs Terms of Service for Google Play Services for AR | No | SJ-33 AR-anchored scan |
| ARKit and SceneKit | Platform SDK | AR tracking, LiDAR scene mesh and rendering on iPhone | https://developer.apple.com/augmented-reality/arkit/ | Apple Developer Program License Agreement | No | SJ-33 AR-anchored scan |
| YouTube home tour videos (India) | Dataset source | Candidate frames for the Indian-home detector dataset | https://www.youtube.com/t/terms | Per video, recorded in the manifest: Creative Commons BY (reuse allowed) or the YouTube standard license. Flagged for legal: the YouTube terms of service restrict downloading; use is internal training only, never redistributed | Yes (internal only) | SJ-126 YouTube source finder |
| YouTube Data API v3 | Service API | Records each candidate video's license and availability; optional search backend | https://developers.google.com/youtube/terms/api-services-terms-of-service | YouTube API Services Terms of Service | No | SJ-126 YouTube source finder |
| yt-dlp 2026.10.26 | Library (Python) | Searches YouTube for candidate videos and downloads kept segments in services/dataset | https://github.com/yt-dlp/yt-dlp | Unlicense | No | SJ-126 YouTube source finder |
| FFmpeg and ffprobe | Tool | Cuts downloaded segments, checks each clip's length and selects frames, on the founder's Windows PC | https://ffmpeg.org/legal.html | LGPL-2.1-or-later, or GPL-2.0-or-later for builds with GPL parts (common Windows builds are GPL). Run as a separate program, not linked or shipped | No | SJ-128 Windows segment downloader |
| yt-dlp-ejs 0.8.0 | Library (Python) | Solves YouTube's player challenges for yt-dlp | https://github.com/yt-dlp/ejs | Unlicense AND MIT AND ISC | No | SJ-128 Windows segment downloader |
| deno 2.9.8 (Python wheel) | Tool | JavaScript runtime yt-dlp needs for YouTube | https://github.com/denoland/deno | MIT | No | SJ-128 Windows segment downloader |
| mutagen 1.48.1 | Library (Python, through yt-dlp) | Media metadata in yt-dlp; installed only with the dataset tools | https://github.com/quodlibet/mutagen | GPL-2.0-or-later. Flagged for legal: used only by internal tooling, never shipped in the app or services | No | SJ-128 Windows segment downloader |
| pycryptodomex 3.24.2, websockets 17.4, requests 2.34.2, brotli 1.2.1, certifi | Library (Python, through yt-dlp) | Network and decryption support for yt-dlp | https://pypi.org/project/yt-dlp/ | BSD and public domain; BSD-3-Clause; Apache-2.0; MIT; MPL-2.0 | No | SJ-128 Windows segment downloader |
| bradautomates/claude-video | Reference code (ideas only, no code copied) | Frame selection ideas reimplemented in services/dataset frames.py: one ffmpeg pass selecting scene changes with showinfo timestamps, interval fallback, and near-duplicate removal by 16x16 thumbnail difference | https://github.com/bradautomates/claude-video | MIT | No | SJ-129 Frame sampling |
| YuNet face detector (face_detection_yunet_2023mar.onnx) | Model | Finds faces so they are blurred before any frame is stored | https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet | MIT | No | SJ-129 Frame sampling |
| opencv-python-headless 5.0.0.93 | Library (Python) | Image decoding, blur score, hashing, face blur in services/dataset | https://github.com/opencv/opencv-python | Apache-2.0 | No | SJ-129 Frame sampling |
| numpy 2.5.5 | Library (Python) | Image arrays in services/dataset | https://github.com/numpy/numpy | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | No | SJ-129 Frame sampling |
| Android SDK, build tools and NDK | Build tools | Compiling the Android app | https://developer.android.com/studio/terms | Android Software Development Kit License Agreement | No | Existing |
| Xcode and the iOS SDK | Build tools | Compiling the iOS app (on EAS Build) | https://developer.apple.com/support/terms/ | Xcode and Apple SDKs Agreement | No | Existing |
| @eslint/js 10.0.1 | Library (npm) | Build and test tooling in root | https://github.com/eslint/eslint | MIT | No | Existing |
| @expo-google-fonts/geist 0.4.2 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/google-fonts | MIT AND OFL-1.1 | No | Existing |
| @expo-google-fonts/instrument-serif 0.4.1 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/google-fonts | MIT AND OFL-1.1 | No | Existing |
| @expo/ui 58.0.28 | Library (npm) | App and service code in apps/mobile, packages/ui | https://github.com/expo/expo | MIT | No | Existing |
| @react-native-async-storage/async-storage 2.2.0 | Library (npm) | App and service code in apps/mobile | https://github.com/react-native-async-storage/async-storage | MIT | No | Existing |
| @shopify/react-native-skia 2.14.0 | Library (npm) | App and service code in apps/mobile, packages/ui | https://github.com/Shopify/react-native-skia | MIT | No | Existing |
| @testing-library/react-native 14.1.0 | Library (npm) | Build and test tooling in apps/mobile, packages/ui | https://www.github.com/callstack/react-native-testing-library | MIT | No | Existing |
| @types/jest 30.0.0 | Library (npm) | Build and test tooling in apps/mobile, packages/ui | https://github.com/DefinitelyTyped/DefinitelyTyped | MIT | No | Existing |
| @types/node 22.20.5 | Library (npm) | Build and test tooling in packages/schemas | https://github.com/DefinitelyTyped/DefinitelyTyped | MIT | No | Existing |
| @types/react 19.3.0 | Library (npm) | Build and test tooling in apps/mobile, packages/ui | https://github.com/DefinitelyTyped/DefinitelyTyped | MIT | No | Existing |
| ajv 8.20.0 | Library (npm) | App and service code in packages/schemas | https://github.com/ajv-validator/ajv | MIT | No | Existing |
| ajv-formats 3.0.1 | Library (npm) | App and service code in packages/schemas | https://github.com/ajv-validator/ajv-formats | MIT | No | Existing |
| eslint 10.15.0 | Library (npm) | Build and test tooling in root | https://github.com/eslint/eslint | MIT | No | Existing |
| expo 58.0.25 | Library (npm) | App and service code in apps/mobile, packages/ui | https://github.com/expo/expo | MIT | No | Existing |
| expo-blur 58.0.6 | Library (npm) | App and service code in apps/mobile, packages/ui | https://github.com/expo/expo | MIT | No | Existing |
| expo-build-properties 58.0.12 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| expo-constants 58.0.16 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| expo-dev-client 58.0.20 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| expo-device 58.0.5 | Library (npm) | App and service code in apps/mobile, packages/ui | https://github.com/expo/expo | MIT | No | Existing |
| expo-font 58.0.12 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| expo-haptics 58.0.8 | Library (npm) | App and service code in apps/mobile, packages/ui | https://github.com/expo/expo | MIT | No | Existing |
| expo-image-manipulator 58.0.16 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| expo-linking 58.0.17 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| expo-localization 58.0.5 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| expo-router 58.0.31 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| expo-sensors 58.0.5 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| expo-status-bar 58.0.5 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| expo-symbols 58.0.5 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| expo-updates 58.0.22 | Library (npm) | App and service code in apps/mobile | https://github.com/expo/expo | MIT | No | Existing |
| globals 17.14.0 | Library (npm) | Build and test tooling in root | https://github.com/sindresorhus/globals | MIT | No | Existing |
| i18next 27.1.1 | Library (npm) | App and service code in apps/mobile | https://github.com/i18next/i18next | MIT | No | Existing |
| jest 30.5.2 | Library (npm) | Build and test tooling in apps/mobile, packages/ui | https://github.com/jestjs/jest | MIT | No | Existing |
| jest-expo 58.0.14 | Library (npm) | Build and test tooling in apps/mobile, packages/ui | https://github.com/expo/expo | MIT | No | Existing |
| json-schema-to-typescript 16.0.0 | Library (npm) | Build and test tooling in packages/schemas | https://github.com/bcherny/json-schema-to-typescript | MIT | No | Existing |
| openapi-fetch 0.17.0 | Library (npm) | App and service code in packages/api-client | https://github.com/openapi-ts/openapi-typescript | MIT | No | Existing |
| openapi-typescript 7.13.0 | Library (npm) | Build and test tooling in packages/api-client | https://github.com/openapi-ts/openapi-typescript | MIT | No | Existing |
| prettier 3.10.1 | Library (npm) | Build and test tooling in root | https://github.com/prettier/prettier | MIT | No | Existing |
| react 19.3.0 | Library (npm) | App and service code in apps/mobile, packages/ui | https://github.com/react/react | MIT | No | Existing |
| react-i18next 18.0.1 | Library (npm) | App and service code in apps/mobile | https://github.com/i18next/react-i18next | MIT | No | Existing |
| react-native 0.88.1 | Library (npm) | App and service code in apps/mobile, packages/ui | https://github.com/react/react-native | MIT | No | Existing |
| react-native-nitro-image 0.15.2 | Library (npm) | App and service code in apps/mobile | https://github.com/mrousavy/react-native-nitro-image | MIT | No | Existing |
| react-native-nitro-modules 0.37.2 | Library (npm) | App and service code in apps/mobile | https://github.com/margelo/nitro | MIT | No | Existing |
| react-native-reanimated 4.7.1 | Library (npm) | App and service code in apps/mobile, packages/ui | https://github.com/software-mansion/react-native-reanimated | MIT | No | Existing |
| react-native-safe-area-context 5.11.1 | Library (npm) | App and service code in apps/mobile | https://github.com/appandflow/react-native-safe-area-context | MIT | No | Existing |
| react-native-screens 4.30.1 | Library (npm) | App and service code in apps/mobile | https://github.com/software-mansion/react-native-screens | MIT | No | Existing |
| react-native-vision-camera 5.2.4 | Library (npm) | App and service code in apps/mobile | https://github.com/margelo/react-native-vision-camera | MIT | No | Existing |
| react-native-vision-camera-worklets 5.2.4 | Library (npm) | App and service code in apps/mobile | https://github.com/margelo/react-native-vision-camera | MIT | No | Existing |
| react-native-worklets 0.13.0 | Library (npm) | App and service code in apps/mobile, packages/ui | https://github.com/software-mansion/react-native-reanimated | MIT | No | Existing |
| typescript 6.0.3 | Library (npm) | Build and test tooling in apps/mobile, packages/api-client, packages/schemas, packages/ui, root | https://github.com/microsoft/TypeScript | Apache-2.0 | No | Existing |
| typescript-eslint 8.72.2 | Library (npm) | Build and test tooling in root | https://github.com/typescript-eslint/typescript-eslint | MIT | No | Existing |
| vitest 5.1.0 | Library (npm) | Build and test tooling in packages/api-client, packages/schemas | https://github.com/vitest-dev/vitest | MIT | No | Existing |
| zustand 5.1.0 | Library (npm) | App and service code in apps/mobile | https://github.com/pmndrs/zustand | MIT | No | Existing |
| boto3 1.44.3 | Library (Python) | Service code in services/api | https://github.com/boto/boto3 | Apache-2.0 | No | Existing |
| datamodel-code-generator 0.96.0 | Library (Python) | Build and test tooling in root | https://github.com/datamodel-code-generator/datamodel-code-generator | MIT | No | Existing |
| fastapi 0.163.0 | Library (Python) | Service code in services/api | https://github.com/fastapi/fastapi | MIT | No | Existing |
| httpx 0.28.1 | Library (Python) | Build and test tooling in root; service code in services/dataset | https://github.com/encode/httpx | BSD-3-Clause | No | Existing |
| jsonschema 4.26.0 | Library (Python) | Build and test tooling in root | https://github.com/python-jsonschema/jsonschema | MIT | No | Existing |
| mypy 2.4.1 | Library (Python) | Build and test tooling in root | https://github.com/python/mypy | MIT | No | Existing |
| psycopg 3.3.9 | Library (Python) | Service code in services/api | https://github.com/psycopg/psycopg | LGPL-3.0-only | No | Existing |
| pydantic 2.14.3 | Library (Python) | Service code in packages/schemas, services/dataset | https://github.com/pydantic/pydantic | MIT | No | Existing |
| pydantic-settings 2.16.3 | Library (Python) | Service code in services/api | https://github.com/pydantic/pydantic-settings | MIT | No | Existing |
| pyjwt 2.15.1 | Library (Python) | Service code in services/api | https://github.com/jpadilla/pyjwt | MIT | No | Existing |
| pytest 9.2.0 | Library (Python) | Build and test tooling in root | https://github.com/pytest-dev/pytest | MIT | No | Existing |
| pytest-asyncio 1.5.0 | Library (Python) | Build and test tooling in root | https://github.com/pytest-dev/pytest-asyncio | Apache-2.0 | No | Existing |
| ruff 0.17.5 | Library (Python) | Build and test tooling in root | https://github.com/astral-sh/ruff | MIT | No | Existing |
| structlog 26.1.0 | Library (Python) | Service code in services/api | https://github.com/hynek/structlog | MIT OR Apache-2.0 | No | Existing |
| types-jsonschema 4.26.0.20261006 | Library (Python) | Build and test tooling in root | https://github.com/python/typeshed | Apache-2.0 | No | Existing |
| uvicorn 0.54.0 | Library (Python) | Service code in services/api | https://github.com/encode/uvicorn | BSD-3-Clause | No | Existing |
| gsplat 1.5.3 | Library | Gaussian splat training and rendering (twin appearance) | https://github.com/nerfstudio-project/gsplat | Apache 2.0 | No | SJ-116 twin risk spike |
| PyTorch 2.4.1 and torchvision 0.19.1 | Library | GPU runtime for all spike models | https://github.com/pytorch/pytorch | BSD 3-clause | No | SJ-116 twin risk spike |
| Grounding DINO base (IDEA-Research) | Model | Open-vocabulary object detection and naming | https://huggingface.co/IDEA-Research/grounding-dino-base | Apache 2.0 | No | SJ-116 twin risk spike |
| YOLOE-26x-seg (Ultralytics 8.4.214) | Model and library | Default open-vocabulary detector for twin objects (SJ-109); compared with Grounding DINO in the spike | https://github.com/ultralytics/ultralytics | AGPL-3.0 (Ultralytics also sells an enterprise license). Legal decision needed before launch: AGPL-3.0 for server-side commercial use, or an Ultralytics enterprise license | No | SJ-116 twin risk spike |
| Ultralytics CLIP | Library | Text tokenizer for YOLOE class prompts | https://github.com/ultralytics/CLIP | AGPL-3.0. Legal decision needed before launch: AGPL-3.0 for server-side commercial use, or an Ultralytics enterprise license | No | SJ-116 twin risk spike |
| MobileCLIP2 text encoder (Apple) | Model | Text embeddings for YOLOE class prompts (downloaded by Ultralytics) | https://huggingface.co/apple/MobileCLIP2-B | Apple ML Research Model Terms of Use (apple-amlr); code MIT. Legal decision needed before launch: research-only model terms for commercial use | No | SJ-116 twin risk spike |
| SAM 2.1 Hiera Large (Meta) | Model | Object masks from detector boxes | https://huggingface.co/facebook/sam2.1-hiera-large | Apache 2.0 | No | SJ-116 twin risk spike |
| SAM 2.1 Hiera Base Plus (Meta), revision b7320756 | Model | Fallback object masks from detector boxes in the twin worker | https://huggingface.co/facebook/sam2.1-hiera-base-plus | Apache 2.0 | No | Twin worker v1 |
| MapAnything (Meta), code at commit 3d10cf7a | Library | Metric multi-view geometry | https://github.com/facebookresearch/map-anything | Apache 2.0 | No | SJ-116 twin risk spike |
| MapAnything checkpoint `facebook/map-anything` | Model | Metric depth without LiDAR from images, intrinsics and AR poses | https://huggingface.co/facebook/map-anything | CC BY-NC 4.0 (an Apache 2.0 checkpoint, `facebook/map-anything-apache`, also exists) | No | SJ-116 twin risk spike |
| MapAnything checkpoint `facebook/map-anything-apache`, revision 00f9c245 | Model | No-LiDAR depth benchmark (not chosen) | https://huggingface.co/facebook/map-anything-apache | Apache 2.0 | No | Twin no-LiDAR depth benchmark |
| Depth Anything 3 Metric Large `depth-anything/DA3METRIC-LARGE`, revision 4010e39f | Model | Metric depth from one image; fallback for phones without LiDAR | https://huggingface.co/depth-anything/DA3METRIC-LARGE | Apache 2.0 | No | Twin no-LiDAR depth benchmark |
| Depth Anything 3 code (ByteDance Seed), commit 3d835ec1 | Library | Runs Depth Anything 3 | https://github.com/ByteDance-Seed/Depth-Anything-3 | Apache 2.0 | No | Twin no-LiDAR depth benchmark |
| addict 2.4.0 | Library | Imported by the Depth Anything 3 code | https://github.com/mewwts/addict | MIT | No | Twin no-LiDAR depth benchmark |
| MoGe-3 ViT-L `Ruicheng/moge-3-vitl`, revision 184008f8 | Model | Metric depth from one image; primary for phones without LiDAR | https://huggingface.co/Ruicheng/moge-3-vitl | MIT | No | Twin no-LiDAR depth benchmark |
| MoGe code (Microsoft), commit 74fbce05, with FlexGEMM | Library | Runs MoGe-3 | https://github.com/microsoft/MoGe | MIT (DINOv2 parts Apache 2.0); FlexGEMM MIT | No | Twin no-LiDAR depth benchmark |
| LaMa big-lama | Model | Inpaints keyframes when an object is removed from the twin (fill B), in the twin worker | https://github.com/advimman/lama | Apache 2.0 | No | SJ-116 twin risk spike; twin object removal |
| simple-lama-inpainting v0.1.0 TorchScript export | Model file | Packaged big-lama weights, pinned by SHA-256 7ba7aa7a, loaded by the twin worker | https://github.com/enesmsahin/simple-lama-inpainting | Apache 2.0 | No | SJ-116 twin risk spike; twin object removal |
| Qwen-Image `Qwen/Qwen-Image`, revision 75e0b4be | Model | Diffusion inpainting compared with LaMa for object removal (not chosen) | https://huggingface.co/Qwen/Qwen-Image | Apache 2.0 | No | Twin object removal comparison |
| Qwen-Image Lightning LoRA, 8 steps V2.0, revision d468c534 | Model | Fast sampling for Qwen-Image in the comparison | https://huggingface.co/lightx2v/Qwen-Image-Lightning | Apache 2.0 | No | Twin object removal comparison |
| diffusers 0.43.0 (Hugging Face) | Library | Runs Qwen-Image inpainting | https://github.com/huggingface/diffusers | Apache 2.0 | No | Twin object removal comparison |
| Transformers 5.23.0, Accelerate 1.15.0, PEFT 0.21.3 (Hugging Face) | Library | Qwen-Image text encoder, loading and LoRA | https://github.com/huggingface | Apache 2.0 | No | Twin object removal comparison |
| PyTorch 2.8.0 | Library | GPU runtime for the comparison and depth benchmark images | https://github.com/pytorch/pytorch | BSD 3-clause | No | Twin object removal comparison |
| LPIPS 0.1.4 | Library and model | Perceptual image distance for scoring fills | https://github.com/richzhang/PerceptualSimilarity | BSD 2-clause | No | Twin object removal comparison |
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


Libraries are the direct dependencies in the workspace manifests (`package.json`, `pyproject.toml`) and the native modules; their own dependencies are not listed one by one. Versions are those installed when the row was added; the lockfiles hold the exact versions in use.
