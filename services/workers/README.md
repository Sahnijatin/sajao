# Workers

Durable pipeline steps. GPU steps run on Modal and call models only through the model gateway.

## Steps

`sajao_workers.steps` is the durable layer every step runs on.

```python
runner = StepRunner(LocalArtifactStore(volume_root))
frames = runner.store.put_blob(package_bytes)
result = await runner.run(objects_step, {"package": frames}, {"detector": "yoloe"})
```

- **Key.** A step's key is the hash of its name, version, input blob digests and params. Bump `version` when the step's code or pinned models change.
- **Run once.** A stored result is returned with `cached=True` and zero cost. A job resumes by calling its steps again: finished ones return at once.
- **Retry alone.** A failing step is retried with backoff; `NonRetryableStepError` stops at once. Nothing is stored until the step succeeds, and the manifest is written after every output blob.
- **One runner at a time.** A lease stops two workers running the same step. An expired lease is taken over.
- **Spend.** Each result records GPU seconds and cost, reported per run.

`LocalArtifactStore` works on a local disk or a mounted Modal volume. The job table and live status for the app are part of the durable job pipeline task, built on top of this layer.

## GPU models

Every GPU model runs in one Modal function, `run_model` in `gpu/app.py`, capped at three containers, so the pipeline never holds more than three GPUs. Callers reach it only through the model gateway:

- `sajao_workers.gpu.GpuModelProvider` is one pinned model on that function. It reserves its time limit against spend caps and charges the measured GPU seconds at the pinned price (`GPU_USD_PER_SECOND`, `INR_PER_USD`).
- `sajao_workers.models` pins each chain, primary first: detection (YOLOE, then Grounding DINO) and masks (SAM 2.1 large, then base plus).
- `sajao_workers.validate` checks every output against its request: same frames in order, classes from the vocabulary, boxes inside the image, one mask per box.

Inputs and outputs are blobs on the `sajao-twin` volume, passed by digest.

```bash
uv run --with 'modal[api-proxy-support]==1.6.4' modal run services/workers/gpu/app.py::smoke
modal billing report --for today -r h --json   # billed spend per app, reported in each PR
```

## Twin steps

- **Objects** (`sajao_workers.twin.objects_step`): detect and segment through the gateway chains, lift each mask with its frame's depth (LiDAR, or the depth step on phones without it), fuse across frames on 5 cm voxels, and fit an upright box by code. Every size is a `Dimension` with source `estimated` and an error band (`ERROR_BANDS`). Boxes are in the capture's world frame; assembly converts them to the space frame.

```bash
uv run --with 'modal[api-proxy-support]==1.6.4' modal run services/workers/gpu/app.py::objects_smoke
```
- **Splat** (`sajao_workers.twin.splat_step`): train the room splat with per-camera pose and exposure refinement (gsplat 1.5.3, `gpu/splat_gpu.py`, ported from the spike), seeded from depth points, with every eighth keyframe held out. Each Gaussian joins an object by mask votes at the refined poses. The GPU writes the splat, labels and refined cameras straight to the store; the step records them by digest. A splat under 20 dB on held-out views fails validation.

```bash
uv run --with 'modal[api-proxy-support]==1.6.4' modal run services/workers/gpu/app.py::splat_smoke
```

## From capture to frames

`sajao_workers.capture_depth` reads the capture package's SJDEPTH1 depth file (format in `docs/06-room-capture.md`); only high-confidence readings place points. `sajao_workers.twin.capture_frames.frames_manifest` turns a capture package into the frames manifest the objects and splat steps read: AR poses (camera +Y up, -Z forward) become OpenCV cameras, intrinsics become matrices, and depth becomes a millimetre PNG per keyframe. A capture without AR poses is refused (`CaptureError`). Depth from LiDAR keeps the LiDAR error band; ARCore depth uses the wider image band.
