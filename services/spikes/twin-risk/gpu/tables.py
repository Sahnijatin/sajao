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


def objects_table() -> str:
    rows = [
        "| Scene | Detector | Depth | GT objects | Found | Recall (class, IoU 0.25) | Recall (any class) | "
        "Precision | Centre error | Length / width / height error | Size error |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    combos = [(d, m) for d in ("gdino", "yoloe") for m in ("lidar", "mapanything")]
    agg: dict[tuple[str, str], list] = {c: [] for c in combos}
    for s in ARKIT:
        for det, mode in combos:
            r = load(s, f"objects_{det}_{mode}.json")
            if not r or not r.get("metrics"):
                rows.append(f"| {s} | {det} | {mode} | failed or not run | | | | | | | |")
                continue
            m = r["metrics"]
            agg[(det, mode)].append(m)
            rows.append(
                f"| {s.replace('arkit_', '')} | {det} | {mode} | {m['gt_objects']} | {r['instances']} | "
                f"{pct(m['recall_class_iou25'])} | {pct(m['recall_any_class_iou25'])} | "
                f"{pct(m['precision_class_iou25'])} | {cm(m['median_center_error_m'])} | "
                f"{cm(m['median_length_error_m'])} / {cm(m['median_width_error_m'])} / "
                f"{cm(m['median_height_error_m'])} | {pct(m['median_size_error_rel'])} |"
            )
    for (det, mode), ms in agg.items():
        if not ms:
            continue
        gt = sum(m["gt_objects"] for m in ms)
        found = sum(round(m["recall_class_iou25"] * m["gt_objects"]) for m in ms)
        loose = sum(round((m["recall_class_iou05"] or 0) * m["gt_objects"]) for m in ms)

        def med(k: str, ms: list = ms) -> list:
            return sorted(m[k] for m in ms if m[k] is not None)

        mid = lambda xs: xs[len(xs) // 2] if xs else None  # noqa: E731
        rows.append(
            f"| **All 5** | **{det}** | **{mode}** | {gt} | | **{found / gt:.0%}** | | | "
            f"{cm(mid(med('median_center_error_m')))} | | {pct(mid(med('median_size_error_rel')))} |"
        )
        rows.append(
            f"|  | {det} | {mode}, loose match (IoU 0.05) | | | {loose / gt:.0%} | | | | | |"
        )
    return "\n".join(rows)


def splat_table() -> str:
    rows = [
        "| Scene | Train views | Gaussians | Train time | PSNR (held-out) | SSIM |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for s in ARKIT + OTHER:
        r = load(s, "splat.json")
        if not r:
            rows.append(f"| {s} | not run | | | | |")
            continue
        rows.append(
            f"| {s} | {r['train_views']} | {r['gaussians'] / 1e6:.2f} M | {r['train_seconds'] / 60:.1f} min | "
            f"{r['psnr']:.1f} dB | {r['ssim']:.3f} |"
        )
    return "\n".join(rows)


def edit_table() -> str:
    rows = [
        "| Scene | Hidden object | Split mask IoU (object / all) | Hole covered: hidden / A / B | "
        "Detector still sees it: photo / hidden / A / B | Time A | Time B |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in ARKIT + OTHER:
        r = load(s, "edit.json")
        if not r:
            rows.append(f"| {s} | not run | | | | | |")
            continue
        h = r["hidden_object"]
        v = r["views"][0] if r["views"] else None
        cov = v["alpha_in_hole"] if v else {}
        det = v["detector_score_for_object"] if v else {}
        t = r["timings"]
        rows.append(
            f"| {s} | {h['label']} | {f(h['split_mask_iou'])} / {f(r['split_mask_iou_mean'])} | "
            f"{pct(cov.get('removed'))} / {pct(cov.get('fill_a'))} / {pct(cov.get('fill_b'))} | "
            f"{f(det.get('photo'))} / {f(det.get('removed'))} / {f(det.get('fill_a'))} / {f(det.get('fill_b'))} | "
            f"{t['fill_a_seconds']:.0f} s | {t['fill_b_seconds'] / 60:.1f} min |"
        )
    return "\n".join(rows)


def phone_table() -> str:
    rows = [
        "| Scene | Variant | Gaussians | PLY | SOG (SH3) | SOG (SH0) | SPZ | PSNR SH3 / SH0 / SOG | "
        "Render ms L40S / L4 / T4 (720x1280) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    mb = lambda b: f(None if b is None else b / 1e6, "{:.1f} MB")  # noqa: E731
    for s in ARKIT + OTHER:
        vs = load(s, "phone_variants.json") or []
        for v in vs:
            rows.append(
                f"| {s} | {v['variant']} | {v['gaussians'] / 1e6:.2f} M | {mb(v.get('ply_bytes'))} | "
                f"{mb(v.get('sog_sh3_bytes'))} | {mb(v.get('sog_sh0_bytes'))} | {mb(v.get('spz_bytes'))} | "
                f"{f(v.get('psnr_sh3'), '{:.1f}')} / {f(v.get('psnr_sh0'), '{:.1f}')} / "
                f"{f(v.get('psnr_sog_decoded'), '{:.1f}')} | "
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
        "## Objects versus ARKitScenes ground truth",
        "",
        objects_table(),
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
