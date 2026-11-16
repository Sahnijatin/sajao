# Object removal comparison

Fill B (per-frame inpainting, then a splat fine-tune) with LaMa versus Qwen-Image, on the objects the SJ-116 spike hid. Internal evaluation on public datasets only. The report is [`eval/twin-removal/REPORT.md`](../../../eval/twin-removal/REPORT.md).

| Path | What |
| --- | --- |
| `gpu/app.py` | Modal app: stages run one after another, each capped, never more than three GPUs |
| `gpu/removal.py` | Holes, known-truth holes, LaMa, splat fine-tune and scores (spike image) |
| `gpu/qwen.py` | Qwen-Image inpainting, Lightning and full settings (diffusers image) |
| `gpu/prep_io.py` | Light file helpers shared by both images |

```bash
M="uv run --with modal[api-proxy-support]==1.6.4 modal run services/spikes/twin-removal/gpu/app.py"
$M --stage prepare && $M --stage qwen && $M --stage refill && $M --stage ablation
```

Finished Qwen-Image runs are reused. Results are written to the `sajao-twin-risk` volume under `out/<room>/removal/<kind>/`.
