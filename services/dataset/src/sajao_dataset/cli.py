"""Command line entry point: `python -m sajao_dataset find ...`."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from sajao_dataset.manifest import append_records, read_manifest
from sajao_dataset.prefilter import decide, write_decisions
from sajao_dataset.queries import QUERIES, QUERY_SET
from sajao_dataset.youtube import DataApiSearch, Search, YtDlpSearch, find

DEFAULT_MANIFEST = Path("data/sources.jsonl")
DEFAULT_PREFILTER = Path("data/prefilter.jsonl")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sajao-dataset")
    commands = parser.add_subparsers(dest="command", required=True)

    find_cmd = commands.add_parser("find", help="Find candidate YouTube home tours")
    find_cmd.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    find_cmd.add_argument("--backend", choices=["auto", "yt-dlp", "data-api"], default="auto")
    find_cmd.add_argument("--per-query", type=int, default=20, help="Results per query and pass")
    find_cmd.add_argument("--max-new", type=int, default=500, help="New videos to add this run")
    find_cmd.add_argument("--query", action="append", help="Run only these queries (repeatable)")

    pre_cmd = commands.add_parser("prefilter", help="Drop builder and designer promos")
    pre_cmd.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    pre_cmd.add_argument("--out", type=Path, default=DEFAULT_PREFILTER)

    args = parser.parse_args(argv)
    if args.command == "find":
        return _find(args)
    if args.command == "prefilter":
        return _prefilter(args)
    return 2


def _find(args: argparse.Namespace) -> int:
    search = _backend(args.backend)
    existing = read_manifest(args.manifest)
    records = find(
        search,
        args.query or QUERIES,
        query_set=QUERY_SET if not args.query else "ad-hoc",
        seen={r.video_id for r in existing},
        per_query=args.per_query,
        max_new=args.max_new,
    )
    added = append_records(args.manifest, records)
    licenses = Counter(r.license for r in records)
    print(
        f"{added} new videos via {search.name} ({dict(licenses)}); "
        f"{len(existing) + added} in {args.manifest}"
    )
    return 0


def _prefilter(args: argparse.Namespace) -> int:
    records = read_manifest(args.manifest)
    decisions = [decide(r) for r in records]
    write_decisions(args.out, decisions)
    kept = [r for r, d in zip(records, decisions, strict=True) if d.keep]
    reasons = Counter(d.reason for d in decisions if not d.keep)
    print(f"{len(kept)} of {len(records)} kept; dropped by reason: {dict(reasons.most_common())}")
    print(f"kept by license: {dict(Counter(r.license for r in kept))}")
    return 0


def _backend(choice: str) -> Search:
    key = os.environ.get("YOUTUBE_API_KEY")
    if choice == "data-api" or (choice == "auto" and key):
        if not key:
            sys.exit("Set YOUTUBE_API_KEY to use the YouTube Data API backend.")
        return DataApiSearch(key)
    return YtDlpSearch()
