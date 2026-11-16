# Render bake-off

Five ways to render a redesigned room, scored blind and by automatic checks (Notion SJ-24, scope change SJ-SCOPE-15). Internal evaluation only: public twin datasets and public listing photos, never shipped. The report is [`eval/render-bakeoff/REPORT.md`](../../../eval/render-bakeoff/REPORT.md).

| Arm | What | Code |
| --- | --- | --- |
| A | Splat of the twin (cleared where furniture is replaced) plus product assets at Design positions, Cycles shadows | `gpu/bk/compose.py` |
| B | Region-by-region edits of the real keyframe photo with product reference images, item checks, up to 2 retries | `gpu/bk/passes.py` (`arm_b`), `gpu/bk/gemini.py` |
| C1 | A plus a generative lighting pass, checks only | `gpu/bk/passes.py`, `gpu/bk/run.py` |
| C2 | C1 with the lock: product pixels from A, only smooth light from the pass | `src/bakeoff/lock.py` |
| C3 | C2 on the real keyframe photo; only cleared regions come from the filled splat | `gpu/bk/compose.py` (`keyframe_background`) |

Also measured: the per-SKU fidelity gate for generated 3D assets (`gpu/bk/fidelity.py`, thresholds in `src/bakeoff/gate.py`) and cost per design.

## Layout

| Path | What |
| --- | --- |
| `src/bakeoff/` | Pure, tested: metrics (IoU, CIEDE2000, edge F1, depth error), the lock, gate calibration |
| `tests/` | Tests for the pure parts |
| `local/fetch_listings.py` | Collects about 100 IKEA India and Wooden Street listings (manifest in the repo, photos only on the private volume) |
| `local/designs.py` | Hand-placed designs by explicit rules, 3 per room, validated against `design.schema.json`; hero keyframe choice |
| `gpu/app.py` | Modal app: images, volume, one function per stage, at most three GPUs at once |
| `gpu/bk/` | GPU jobs: cutouts and image-to-3D, fidelity gate, twin survey and clearing, compositor, passes, checks |

## Rerun

```bash
M="modal run services/spikes/render-bakeoff/gpu/app.py"
$M --stage survey                       # top-down maps of the twins
$M --stage cutouts && $M --stage triposg && $M --stage gate --model triposg
$M --stage prepare --model triposg      # render-ready assets for designs
python services/spikes/render-bakeoff/local/designs.py WORK_DIR
$M --stage clear && $M --stage compose && $M --stage generate && $M --stage check
```

The Gemini arm needs a Modal secret `gcp` with `GCP_SA_KEY`. TRELLIS.2 and SAM 3D Objects need a Modal secret `huggingface` with `HF_TOKEN` for an account that accepted the DINOv3 and SAM 3D Objects licenses.
