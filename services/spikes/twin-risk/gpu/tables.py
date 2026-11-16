"""Build the results tables for eval/twin-risk/ from the collected JSON.

python services/spikes/twin-risk/gpu/tables.py  ->  eval/twin-risk/tables.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RES = ROOT / "eval" / "twin-risk" / "results"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from twin_risk.costs import GPU_USD_PER_SECOND, cpu_cost_usd  # noqa: E402

ARKIT = [
    "arkit_living_47331265",
    "arkit_living_41159541",
    "arkit_living_41159566",
    "arkit_bedroom_47430034",
    "arkit_bedroom_47895350",
]
OTHER = ["room", "kitchen", "counter", "frl_apartment_0", "apartment_1"]


def load(scene: str, name: str):
    p = RES / scene / name
    return json.loads(p.read_text()) if p.exists() else None


def f(v, fmt="{:.2f}", none="n/a"):
    return none if v is None else fmt.format(v)


def pct(v):
    return f(v, "{:.0%}")


def cm(v):
    return f(None if v is None else v * 100, "{:.0f} cm")


def _obj_row(scene, det, mode, poses, r, key):
    m = r[key]
    return (
        f"| {scene.replace('arkit_', '')} | {det} | {mode} | {poses} | {m['gt_objects']} | "
        f"{r['instances']} | {pct(m['recall_class_iou25'])} | {pct(m['recall_any_class_iou25'])} | "
        f"{pct(m['recall_class_iou05'])} | {pct(m['precision_class_iou25'])} | "
        f"{cm(m['median_center_error_m'])} | {cm(m['median_length_error_m'])} / "
        f"{cm(m['median_width_error_m'])} / {cm(m['median_height_error_m'])} | "
        f"{pct(m['median_size_error_rel'])} |"
    )


def objects_table(key: str = "metrics") -> str:
    """key: "metrics" (all annotated objects) or "metrics_seen" (objects in view)."""
    rows = [
        "| Scene | Detector | Depth | Poses | Annotated objects | Instances | Recall, class, IoU 0.25 | "
        "Recall, any class | Recall, class, IoU 0.05 | Precision | Centre error | "
        "Length / width / height error | Size error |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    combos = [
        (d, m, p)
        for d in ("gdino", "yoloe")
        for m in ("lidar", "mapanything")
        for p in ("raw", "refined")
    ]
    agg: dict[tuple[str, str, str], list] = {c: [] for c in combos}
    for s in ARKIT:
        for det, mode, poses in combos:
            r = load(s, f"objects_{det}_{mode}{'' if poses == 'raw' else '_refined'}.json")
            if not r or not r.get(key):
                continue
            agg[(det, mode, poses)].append(r[key])
            rows.append(_obj_row(s, det, mode, poses, r, key))
    rows.append("")
    rows.append(
        "| Detector | Depth | Poses | Annotated objects | Recall, class, IoU 0.25 | Recall, class, IoU 0.05 | "
        "Median centre error | Median size error |"
    )
    rows.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for (det, mode, poses), ms in agg.items():
        if not ms:
            continue
        gt = sum(m["gt_objects"] for m in ms)
        found = sum(round(m["recall_class_iou25"] * m["gt_objects"]) for m in ms)
        loose = sum(round((m["recall_class_iou05"] or 0) * m["gt_objects"]) for m in ms)

        def mid(k: str, ms: list = ms):
            xs = sorted(m[k] for m in ms if m[k] is not None)
            return xs[len(xs) // 2] if xs else None

        rows.append(
            f"| {det} | {mode} | {poses} | {gt} | {found / gt:.0%} | {loose / gt:.0%} | "
            f"{cm(mid('median_center_error_m'))} | {pct(mid('median_size_error_rel'))} |"
        )
    return "\n".join(rows)


def splat_table() -> str:
    rows = [
        "| Scene | Train views | Gaussians | Train time | PSNR, raw poses | PSNR (held-out) | SSIM | "
        "Pose correction (median) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in ARKIT + OTHER:
        r = load(s, "splat.json")
        if not r:
            rows.append(f"| {s} | not run | | | | | | |")
            continue
        corr = (
            f"{r['pose_correction_median_cm']:.1f} cm, {r['pose_correction_median_deg']:.2f} deg"
            if r.get("pose_and_exposure_refined")
            else "none (poses not refined)"
        )
        rows.append(
            f"| {s} | {r['train_views']} | {r['gaussians'] / 1e6:.2f} M | {r['train_seconds'] / 60:.1f} min | "
            f"{f(r.get('psnr_raw_poses'), '{:.1f} dB')} | {r['psnr']:.1f} dB | {r['ssim']:.3f} | {corr} |"
        )
    return "\n".join(rows)


def edit_table() -> str:
    rows = [
        "| Scene | Kind | Hidden object | Split IoU, object / scene mean | Hole covered: hidden / A / B | "
        "Detector score on the object: photo / hidden / A / B | Time A | Time B |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in ARKIT + OTHER:
        r = load(s, "edit.json")
        if not r:
            rows.append(f"| {s} | not run | | | | | | |")
            continue
        for kind, h in r.get("hidden", {}).items():
            if "skipped" in h:
                rows.append(f"| {s} | {kind} | {h['skipped']} | | | | | |")
                continue
            v = h["views"][0] if h["views"] else {}
            cov = v.get("alpha_in_hole", {})
            det = v.get("detector_score_for_object", {})
            t = h["timings"]
            rows.append(
                f"| {s} | {kind} | {h['label']} | {f(h['split_mask_iou'])} / {f(r['split_mask_iou_mean'])} | "
                f"{pct(cov.get('removed'))} / {pct(cov.get('fill_a'))} / {pct(cov.get('fill_b'))} | "
                f"{f(det.get('photo'))} / {f(det.get('removed'))} / {f(det.get('fill_a'))} / {f(det.get('fill_b'))} | "
                f"{t['fill_a_seconds']:.0f} s | {t['fill_b_seconds'] / 60:.1f} min |"
            )
    return "\n".join(rows)


def phone_table() -> str:
    rows = [
        "| Scene | Variant | Decimation | Gaussians | PLY | Compressed PLY | SPZ | SOG (SH0) | "
        "PSNR SH3 / SH0 / SOG SH0 decoded | Render ms SH3, L40S / L4 / T4 (720x1280) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    mb = lambda b: f(None if b is None else b / 1e6, "{:.1f} MB")  # noqa: E731
    for s in ARKIT + OTHER:
        vs = load(s, "phone_variants.json") or []
        for v in vs:
            if "gaussians" not in v:
                continue
            rows.append(
                f"| {s} | {v['variant']} | {v.get('decimate_method', 'none')} | "
                f"{v['gaussians'] / 1e6:.2f} M | {mb(v.get('ply_bytes'))} | "
                f"{mb(v.get('compressed_ply_bytes'))} | {mb(v.get('spz_bytes'))} | "
                f"{mb(v.get('sog_sh0_bytes'))} | "
                f"{f(v.get('psnr_sh3'), '{:.1f}')} / {f(v.get('psnr_sh0'), '{:.1f}')} / "
                f"{f(v.get('psnr_sog_sh0_decoded'), '{:.1f}')} | "
                f"{f(v.get('render_ms_L40S_sh3'), '{:.1f}')} / {f(v.get('render_ms_L4_sh3'), '{:.1f}')} / "
                f"{f(v.get('render_ms_T4_sh3'), '{:.1f}')} |"
            )
    return "\n".join(rows)


def stream_table() -> str:
    rows = [
        "| Scene | GPU | Render ms per frame | Max fps, one stream | H.264 Mbps | JPEG per view | "
        "GPU cost per viewing minute (30 fps) | Light mesh (gzip) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in ARKIT + OTHER:
        st = load(s, "stream.json") or {}
        lm = load(s, "light_mesh.json") or {}
        for gpu, r in st.items():
            rows.append(
                f"| {s} | {gpu} | {r['render_ms_per_frame']:.1f} | {r['max_fps_single_stream']:.0f} | "
                f"{r['h264_crf23_mbps']:.1f} | {r['jpeg_q80_mean_kb']:.0f} KB | "
                f"${r['gpu_cost_per_view_minute_usd_30fps']:.4f} | {f(lm.get('glb_gzip_bytes'), '{:.0f} B')} |"
            )
    return "\n".join(rows)


def cost_table() -> str:
    rows = [
        "| Scene | Stage | Device | Seconds | Cost (USD) |",
        "| --- | --- | --- | --- | --- |",
    ]
    totals: dict[str, float] = {}
    for s in ARKIT + OTHER:
        t = load(s, "timings.json") or {}
        for stage, r in t.items():
            gpu = r["gpu"]
            cost = (
                cpu_cost_usd(8, 16, r["seconds"])
                if gpu == "cpu"
                else GPU_USD_PER_SECOND[gpu] * r["seconds"]
            )
            totals[s] = totals.get(s, 0.0) + cost
            rows.append(f"| {s} | {stage} | {gpu} | {r['seconds']:.0f} | {cost:.3f} |")
    rows.append("")
    rows.append("| Scene | Total spike cost (USD) |")
    rows.append("| --- | --- |")
    rows += [f"| {s} | {c:.2f} |" for s, c in totals.items()]
    return "\n".join(rows)


def main() -> None:
    out = [
        "# Twin risk spike: generated tables",
        "",
        "Generated by `services/spikes/twin-risk/gpu/tables.py` from `results/`.",
        "",
        "## Objects versus ARKitScenes ground truth: all annotated objects",
        "",
        objects_table("metrics"),
        "",
        "## Objects versus ARKitScenes ground truth: objects in view",
        "",
        "Annotated objects whose centre was within 5 m, in frame and not hidden behind a nearer LiDAR "
        "surface in at least 5 frames.",
        "",
        objects_table("metrics_seen"),
        "",
        "## Splat quality",
        "",
        splat_table(),
        "",
        "## Split, hide and fill",
        "",
        edit_table(),
        "",
        "## On-device splat variants",
        "",
        phone_table(),
        "",
        "## Server-rendered views",
        "",
        stream_table(),
        "",
        "## GPU time and cost per scene",
        "",
        cost_table(),
        "",
    ]
    (RES.parent / "tables.md").write_text("\n".join(out))
    print((RES.parent / "tables.md").read_text())


if __name__ == "__main__":
    main()
