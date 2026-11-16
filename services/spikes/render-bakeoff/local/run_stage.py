"""Run one bake-off stage on Modal from Python (more reliable here than the CLI entrypoint).

python services/spikes/render-bakeoff/local/run_stage.py cutouts
python services/spikes/render-bakeoff/local/run_stage.py triposg
python services/spikes/render-bakeoff/local/run_stage.py gate triposg
python services/spikes/render-bakeoff/local/run_stage.py prepare triposg [ids]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "services" / "spikes" / "render-bakeoff" / "gpu"))
import app as A  # noqa: E402

OUT = REPO / "eval" / "render-bakeoff" / "results"


def listings(extras=False):
    d = REPO / "eval" / "render-bakeoff"
    out = json.loads((d / "listings.json").read_text())
    if extras:
        out += json.loads((d / "extras.json").read_text())
    return out


def batched_map(fn, *arg_lists, batch: int = 12):
    """map in batches, printing as results arrive (one large map stalled here)."""
    out = []
    n = len(arg_lists[0])
    for s in range(0, n, batch):
        chunk = [a[s : s + batch] for a in arg_lists]
        for r in fn.map(*chunk, return_exceptions=True):
            rs = r if isinstance(r, list) else [{"error": repr(r)[:500]}]
            out += rs
            print(len(out), "results;", f"call {len(out)}", str(rs[0])[:160], flush=True)
    return out


def room_files() -> dict:
    d = REPO / "eval" / "render-bakeoff" / "designs"
    return {
        f.stem: json.loads(f.read_text())
        for f in sorted(d.glob("*.json"))
        if not f.stem.endswith(".designs")
    }


def stream(fn, *arg_lists):
    """starmap with progress; one result per job (errors kept, not raised)."""
    out = []
    for r in fn.map(*arg_lists, return_exceptions=True):
        out.append(r if not isinstance(r, BaseException) else {"error": repr(r)[:800]})
        print(len(out), "/", len(arg_lists[0]), json.dumps(out[-1], default=str)[:200], flush=True)
    return out


def main(stage: str, model: str = "triposg", only: str = "") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with A.app.run():
        if stage == "cutouts":
            lids = [x["id"] for x in listings(extras=True)]
            res = batched_map(
                A.cutouts, [lids[i : i + 10] for i in range(0, len(lids), 10)], batch=3
            )
            (OUT / "cutouts.json").write_text(json.dumps(res, indent=1, default=str))
            print(
                sum(1 for r in res if r.get("clean")), "of", len(res), "listings have a clean view"
            )
        elif stage == "triposg":
            lids = only.split(",") if only else [x["id"] for x in listings()]
            res = batched_map(A.triposg, [lids[i : i + 5] for i in range(0, len(lids), 5)], batch=2)
            (OUT / "assets_triposg.json").write_text(json.dumps(res, indent=1, default=str))
            print(
                sum(1 for r in res if "error" in r or "skipped" in r),
                "failed or skipped of",
                len(res),
            )
        elif stage in ("trellis2", "sam3d"):
            lids = only.split(",") if only else [x["id"] for x in listings()]
            fn = A.trellis2 if stage == "trellis2" else A.sam3d
            res = batched_map(fn, [lids[i : i + 5] for i in range(0, len(lids), 5)], batch=2)
            (OUT / f"assets_{stage}.json").write_text(json.dumps(res, indent=1, default=str))
            print(
                sum(1 for r in res if "error" in r or "skipped" in r),
                "failed or skipped of",
                len(res),
            )
        elif stage == "parametric":
            lids = only.split(",") if only else [x["id"] for x in listings()]
            chunks = [lids[i : i + 6] for i in range(0, len(lids), 6)]
            picked = batched_map(A.pick_templates, chunks, batch=4)
            (OUT / "parametric_pick.json").write_text(json.dumps(picked, indent=1, default=str))
            built = batched_map(A.build_parametric, chunks, batch=4)
            (OUT / "assets_parametric.json").write_text(json.dumps(built, indent=1, default=str))
            print(
                sum(1 for r in built if "error" in r or "skipped" in r),
                "failed or skipped of",
                len(built),
            )
        elif stage == "gate":
            items = listings()
            rng = random.Random(7)
            by_cat: dict[str, list[str]] = {}
            for x in items:
                by_cat.setdefault(x["category"], []).append(x["id"])
            jobs = [
                [(x["id"], rng.sample([o for o in by_cat[x["category"]] if o != x["id"]], 2))]
                for x in items
            ]
            res = batched_map(A.gate, [model] * len(jobs), jobs)
            (OUT / f"gate_{model}.json").write_text(json.dumps(res, indent=1, default=float))
            print(sum(1 for r in res if "error" in r), "errors of", len(res))
        elif stage == "prepare":
            lids = only.split(",") if only else [x["id"] for x in listings()]
            res = batched_map(A.prepare_assets, [model] * len(lids), [[lid] for lid in lids])
            (OUT / f"prepare_{model}.json").write_text(json.dumps(res, indent=1, default=float))
            print(sum(1 for r in res if "error" in r), "errors of", len(res))
        elif stage in ("clear", "compose", "plant", "pilot", "generate", "check"):
            rooms = room_files()
            sel = only.split(",") if only else []
            jobs = [
                (r, d["id"])
                for r, rf in rooms.items()
                for d in rf["designs"]
                if not sel or r in sel or d["id"] in sel
            ]
            gen = model if model in ("qwen", "flux2k", "gemini") else "qwen"
            if stage == "clear":
                rs = [r for r in rooms if not sel or r in sel]
                res = stream(
                    A.clear,
                    [r for r in rs],
                    [rooms[r]["clear"]["zone"] for r in rs],
                    ["zone"] * len(rs),
                )
            elif stage == "compose":
                res = stream(A.compose, [j[0] for j in jobs], [j[1] for j in jobs])
            elif stage == "plant":
                pj = [(r, d, p) for r, d in jobs for p in A.PLANTED]
                stream(A.compose, *map(list, zip(*pj, strict=True)))
                res = stream(
                    A.check,
                    [p[0] for p in pj],
                    [p[1] for p in pj],
                    [["A"]] * len(pj),
                    [p[2] for p in pj],
                )
            elif stage == "pilot":
                pj = [(r, d, m) for r, d in jobs for m in ("qwen", "flux2k")]
                res = stream(
                    A.generate,
                    [p[0] for p in pj],
                    [p[1] for p in pj],
                    [p[2] for p in pj],
                    [["C1", "C2"]] * len(pj),
                )
            elif stage == "generate" and gen == "gemini":
                res = stream(
                    A.generate_gemini,
                    [j[0] for j in jobs],
                    [j[1] for j in jobs],
                    [["B"]] * len(jobs),
                )
            elif stage == "generate":
                res = stream(
                    A.generate,
                    [j[0] for j in jobs],
                    [j[1] for j in jobs],
                    [gen] * len(jobs),
                    [A.ARMS_OPEN] * len(jobs),
                )
            else:
                arms = ["A", f"C1_{gen}", f"C2_{gen}", f"C3_{gen}", f"B_{gen}"]
                res = stream(
                    A.check, [j[0] for j in jobs], [j[1] for j in jobs], [arms] * len(jobs)
                )
            (OUT / f"{stage}{'_' + gen if stage in ('generate', 'check') else ''}.json").write_text(
                json.dumps(res, indent=1, default=str)
            )
        else:
            raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    main(*sys.argv[1:])
