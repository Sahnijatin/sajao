# No-LiDAR depth benchmark

Compares commercially licensed depth models with MapAnything (CC BY-NC) on the SJ-116 ARKitScenes rooms, with LiDAR as ground truth. Internal evaluation on public datasets only. The report is [`eval/twin-depth/REPORT.md`](../../../eval/twin-depth/REPORT.md).

| Path | What |
| --- | --- |
| `gpu/app.py` | Modal app: one image per model family, GPU calls one at a time, scoring on CPU |
| `gpu/depth_eval.py` | Depth per model, scores against LiDAR, objects lifted through the spike's fusion |

```bash
uv run --with 'modal[api-proxy-support]==1.6.4' modal run services/spikes/twin-depth/gpu/app.py
uv run --with 'modal[api-proxy-support]==1.6.4' modal run services/spikes/twin-depth/gpu/app.py --stage score
```

Finished predictions are reused, so a rerun only pays for what is missing. Results are written to the `sajao-twin-risk` volume as `out/<room>/depth_bench_<model>.json`.
