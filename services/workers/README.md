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
