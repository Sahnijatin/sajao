"""Bake-off analysis: votes, checks, checker calibration, fidelity gate, cost.

    python services/spikes/render-bakeoff/local/analyze.py [votes.json]

Reads eval/render-bakeoff/results/*.json and the vote key (image id -> design, arm).
Writes eval/render-bakeoff/results/summary.json and prints Markdown tables.
"""

from __future__ import annotations

import base64
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
R = REPO / "eval" / "render-bakeoff" / "results"
sys.path.insert(0, str(REPO / "services" / "spikes" / "render-bakeoff" / "src"))
from bakeoff.gate import calibrate, pass_rate, sku_passes  # noqa: E402


def decode(code: str) -> tuple[str, str, list[tuple[int, int]]]:
    """R1-<study>-<voter>-<base64url pairs of (image index, rating)>."""
    _, study, voter, data = code.split("-", 3)
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return study, voter, [(raw[i], raw[i + 1]) for i in range(0, len(raw) - 1, 2)]


def bootstrap(x: np.ndarray, stat=np.mean, n: int = 4000, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    if len(x) == 0:
        return float("nan"), float("nan")
    s = [stat(rng.choice(x, len(x))) for _ in range(n)]
    return float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


def votes_table(codes: list[str], key: dict) -> dict:
    """Per arm: mean rating, share rated 4 or 5 (the existing gate's measure), and
    paired differences against the best B arm within the same design and voter."""
    by_voter = {}
    for c in codes:
        study, voter, pairs = decode(c.strip())
        if study != key["study"]:
            continue
        by_voter[voter] = pairs  # latest code per voter wins
    rows = defaultdict(list)
    per = defaultdict(dict)  # (voter, design) -> arm -> rating
    for voter, pairs in by_voter.items():
        for idx, rating in pairs:
            img = key["images"][idx]
            rows[img["arm"]].append(rating)
            per[(voter, img["design"])][img["arm"]] = rating
    out = {"voters": len(by_voter), "arms": {}}
    for arm, rs in sorted(rows.items()):
        a = np.array(rs, float)
        top = (a >= 4).astype(float)
        out["arms"][arm] = {
            "n": len(a),
            "mean": float(a.mean()),
            "mean_ci": bootstrap(a),
            "top2": float(top.mean()),
            "top2_ci": bootstrap(top),
        }
    b_arms = [a for a in out["arms"] if a.startswith("B_")]
    if b_arms:
        best_b = max(b_arms, key=lambda a: out["arms"][a]["top2"])
        out["best_b"] = best_b
        for arm in out["arms"]:
            d = [v[arm] - v[best_b] for v in per.values() if arm in v and best_b in v]
            out["arms"][arm]["paired_vs_best_b"] = {
                "n": len(d),
                "mean": float(np.mean(d)) if d else None,
                "ci": bootstrap(np.array(d, float)) if d else None,
            }
    return out


def checks_table(gen: str) -> dict:
    f = R / f"check_{gen}.json"
    if not f.exists():
        return {}
    res = json.loads(f.read_text())
    agg = defaultdict(lambda: defaultdict(list))
    for design in res:
        if not isinstance(design, dict) or "error" in design:
            continue
        for arm, r in design.items():
            if not isinstance(r, dict) or r.get("missing"):
                continue
            kind = arm.split("_")[0]
            present = [i for i in r["items"] if i.get("present")]
            agg[kind]["passed"].append(r["passed"])
            agg[kind]["position"].append(all(i["position_ok"] for i in present))
            agg[kind]["recognisable"].append(all(i["recognisable_ok"] for i in present))
            agg[kind]["room"].append(r["room"]["passed"])
            agg[kind]["no_invented"].append(r["invented"]["passed"])
            agg[kind]["aesthetic"].append(r["aesthetic"])
            agg[kind]["item_iou"] += [i["iou"] for i in present]
            agg[kind]["item_emb"] += [i["emb"] for i in present]
    out = {}
    for kind, d in agg.items():
        out[kind] = {k: (float(np.nanmean(v)) if v else None) for k, v in d.items()}
        out[kind]["renders"] = len(d["passed"])
    return out


def planted_table() -> dict:
    """Catch rate on planted errors and false-fail rate on good renders (A and C2)."""
    f = R / "plant.json"
    good = R / "check_qwen.json"
    out = {}
    if f.exists():
        res = [r for r in json.loads(f.read_text()) if isinstance(r, dict) and "A" in r]
        by = defaultdict(list)
        for r, kind in zip(
            res,
            [k for _ in range(len(res) // 4) for k in ("swap", "scale10", "move15", "plant")],
            strict=False,
        ):
            by[kind].append(not r["A"]["passed"])
        out["caught"] = {k: float(np.mean(v)) for k, v in by.items()}
        out["caught_all"] = float(np.mean([x for v in by.values() for x in v])) if by else None
    if good.exists():
        res = json.loads(good.read_text())
        ok = [
            d[a]["passed"]
            for d in res
            if isinstance(d, dict)
            for a in d
            if a in ("A",) or a.startswith("C2_")
            if isinstance(d[a], dict) and "passed" in d[a]
        ]
        out["false_fail_good"] = float(1 - np.mean(ok)) if ok else None
    return out


def gate_table(model: str) -> dict:
    f = R / f"gate_{model}.json"
    if not f.exists():
        return {}
    res = [r for r in json.loads(f.read_text()) if "pairs" in r]
    listings = {
        x["id"]: x
        for x in json.loads((REPO / "eval" / "render-bakeoff" / "listings.json").read_text())
    }
    sys.path.insert(0, str(REPO / "services" / "spikes" / "render-bakeoff" / "local"))
    from designs import plausible

    true_, wrong, cats, ids = [], [], [], []
    for r in res:
        if not plausible(listings[r["id"]]):
            continue
        t = [p for p in r["pairs"] if p.get("true") and "views" in p]
        if not t:
            continue
        true_.append(t[0]["views"])
        cats.append(r["category"])
        ids.append(r["id"])
        wrong += [p["views"] for p in r["pairs"] if not p.get("true") and "views" in p]
    # Calibrate on half the SKUs, report on the other half (and on all, for reference).
    half = np.arange(len(true_)) % 2 == 0
    th, tp_cal, fp_cal = calibrate([v for v, h in zip(true_, half, strict=True) if h], wrong)
    held = [v for v, h in zip(true_, half, strict=True) if not h]
    by_cat = defaultdict(list)
    for v, c in zip(true_, cats, strict=True):
        by_cat[c].append(sku_passes(v, th))
    input_only = [sku_passes([x for x in v if x.get("is_input")] or v[:1], th) for v in true_]
    return {
        "skus": len(true_),
        "implausible_listing_dims": sum(1 for r in res if not plausible(listings[r["id"]])),
        "thresholds": th.__dict__,
        "wrong_sku_pass_rate": fp_cal,
        "pass_rate_calibration_half": tp_cal,
        "pass_rate_held_out_half": pass_rate(held, th),
        "pass_rate_all": pass_rate(true_, th),
        "pass_rate_input_view_only": float(np.mean(input_only)) if input_only else None,
        "by_category": {c: float(np.mean(v)) for c, v in sorted(by_cat.items())},
        "median_view": {
            k: float(np.median([x[k] for v in true_ for x in v])) for k in ("iou", "de", "emb")
        },
    }


ASSET_GPU = {"triposg": "L40S", "trellis2": "H100", "sam3d": "H100"}


def build_costs(model: str) -> dict[str, dict]:
    """Per SKU: build seconds and cost in INR (GPU time at Modal rates; for the
    parametric tier, the vision call's metered cost plus Blender CPU time)."""
    from bakeoff.cost import cpu_usd, gpu_usd, inr

    out: dict[str, dict] = {}
    f = R / f"assets_{model}.json"
    if not f.exists():
        return out
    rows = json.loads(f.read_text())
    if model == "parametric":
        picks = {
            x["id"]: x for x in json.loads((R / "parametric_pick.json").read_text()) if "spec" in x
        }
        for x in rows:
            if "build_seconds" not in x:
                continue
            pk = picks.get(x["id"], {})
            secs = pk.get("seconds", 0) + x["build_seconds"]
            cost = pk.get("cost_micro_inr", 0) / 1e6 + inr(cpu_usd(x["build_seconds"]))
            out[x["id"]] = {"seconds": secs, "inr": cost}
    else:
        for x in rows:
            if "seconds" in x:
                out[x["id"]] = {
                    "seconds": x["seconds"],
                    "inr": inr(gpu_usd(ASSET_GPU[model], x["seconds"])),
                }
    return out


def tier_comparison(models=("triposg", "trellis2", "sam3d", "parametric")) -> dict:
    """Per category and tier: gate pass rate (thresholds calibrated per tier on half
    the SKUs, all SKUs reported), median build seconds, median cost per SKU, and the
    best default tier (highest pass rate; ties to the cheaper)."""
    table: dict[str, dict[str, dict]] = defaultdict(dict)
    for m in models:
        g = gate_table(m)
        if not g:
            continue
        costs = build_costs(m)
        res = [r for r in json.loads((R / f"gate_{m}.json").read_text()) if "pairs" in r]
        cats = defaultdict(list)
        for r in res:
            cats[r["category"]].append(r["id"])
        for cat, ids in cats.items():
            c = [costs[i] for i in ids if i in costs]
            table[cat][m] = {
                "pass_rate": g["by_category"].get(cat),
                "skus_built": len(c),
                "skus": len(ids),
                "median_seconds": float(np.median([x["seconds"] for x in c])) if c else None,
                "median_inr": float(np.median([x["inr"] for x in c])) if c else None,
            }
    best = {}
    for cat, row in table.items():
        cands = [(v["pass_rate"] or 0, -(v["median_inr"] or 1e9), m) for m, v in row.items()]
        if cands:
            best[cat] = max(cands)[2]
    return {"by_category": table, "best_default_tier": best}


def main() -> None:
    summary = {
        "gate": {m: gate_table(m) for m in ("triposg", "trellis2", "sam3d")},
        "checks": {g: checks_table(g) for g in ("qwen", "flux2k", "gemini")},
        "planted": planted_table(),
    }
    key_f = REPO / "eval" / "render-bakeoff" / "voting" / "key.json"
    if len(sys.argv) > 1 and key_f.exists():
        codes = [c for c in Path(sys.argv[1]).read_text().split() if c.startswith("R1-")]
        summary["votes"] = votes_table(codes, json.loads(key_f.read_text()))
    (R / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    print(json.dumps(summary, indent=1, default=float)[:6000])


if __name__ == "__main__":
    main()
