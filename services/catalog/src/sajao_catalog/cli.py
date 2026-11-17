"""sajao-catalog ingest | coverage

sajao-catalog ingest --adapter curated --input listings.json --out catalog.jsonl
sajao-catalog coverage --catalog catalog.jsonl [--placeable]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sajao_catalog.adapters import ADAPTERS
from sajao_catalog.coverage import table
from sajao_catalog.ingest import ingest, load


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sajao-catalog")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="validate listings and upsert them into a catalog")
    i.add_argument("--adapter", choices=sorted(ADAPTERS), required=True)
    i.add_argument("--input", type=Path, required=True)
    i.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("coverage", help="category by style by budget band")
    c.add_argument("--catalog", type=Path, required=True)
    c.add_argument("--placeable", action="store_true", help="gate-passing products only")
    a = p.parse_args(argv)
    if a.cmd == "ingest":
        written, rejected = ingest(ADAPTERS[a.adapter](a.input), a.out)
        print(f"{len(written)} products ingested, {len(rejected)} rejected")
        for r in rejected:
            print(f"  rejected: {r}")
        return 1 if rejected and not written else 0
    print(table(list(load(a.catalog).values()), placeable_only=a.placeable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
