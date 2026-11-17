"""Tally the blind render vote among arms that pass the fidelity gate.

    python eval/render-bakeoff/votes.py codes.txt [voting/key_s2.json]

codes.txt holds answer codes (R1-<study>-<voter>-<data>), one or more per line, from
people who sent them back or pasted on the voting page. The latest code per voter wins.
Arms that fail the gate, and Gemini, are reported for comparison only.
"""

from __future__ import annotations

import base64
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ELIGIBLE = {"A", "C2_qwen", "C3_qwen", "C3L_qwen"}  # REPORT.md, fidelity gate
LAUNCH = ("C3L_qwen", "C3_qwen")  # eligible and photo-based (no 3D twin)


def decode(code: str) -> tuple[str, str, list[tuple[int, int]]]:
    _, study, voter, data = code.split("-", 3)
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return study, voter, [(raw[i], raw[i + 1]) for i in range(0, len(raw) - 1, 2)]


def interval(xs: list[float], n: int = 4000) -> tuple[float, float]:
    rng = random.Random(0)  # noqa: S311 (bootstrap resampling, not security)
    means = sorted(statistics.fmean(rng.choices(xs, k=len(xs))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def tally(codes: list[str], key: dict) -> dict:
    by_voter: dict[str, list[tuple[int, int]]] = {}
    for c in codes:
        study, voter, pairs = decode(c)
        if study == key["study"]:
            by_voter[voter] = pairs
    ratings: dict[str, list[float]] = defaultdict(list)
    per: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for voter, pairs in by_voter.items():
        for idx, rating in pairs:
            img = key["images"][idx]
            ratings[img["arm"]].append(rating)
            per[(voter, img["design"])][img["arm"]] = rating
    arms = {}
    for arm, rs in sorted(ratings.items()):
        arms[arm] = {
            "eligible": arm in ELIGIBLE,
            "n": len(rs),
            "mean": round(statistics.fmean(rs), 2),
            "mean_95": [round(v, 2) for v in interval(rs)] if len(rs) > 1 else None,
            "share_4_or_5": round(sum(r >= 4 for r in rs) / len(rs), 2),
        }
    a, b = LAUNCH
    diffs = [float(v[a] - v[b]) for v in per.values() if a in v and b in v]
    return {
        "study": key["study"],
        "voters": len(by_voter),
        "arms": arms,
        "launch_pair": {
            "arms": [a, b],
            "paired_designs": len(diffs),
            "mean_difference": round(statistics.fmean(diffs), 2) if diffs else None,
            "difference_95": [round(v, 2) for v in interval(diffs)] if len(diffs) > 1 else None,
        },
    }


def main() -> None:
    codes = [w for w in Path(sys.argv[1]).read_text().split() if w.startswith("R1-")]
    key_path = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "voting" / "key_s2.json"
    print(json.dumps(tally(codes, json.loads(key_path.read_text())), indent=1))


if __name__ == "__main__":
    main()
