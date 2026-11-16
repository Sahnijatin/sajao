"""Command line entry point: `python -m sajao_dataset find ...`."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from sajao_dataset.manifest import append_records, read_manifest
from sajao_dataset.queries import QUERIES, QUERY_SET
from sajao_dataset.youtube import DataApiSearch, Search, YtDlpSearch, find

DEFAULT_MANIFEST = Path("data/sources.jsonl")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sajao-dataset")
    commands = parser.add_subparsers(dest="command", required=True)

    find_cmd = commands.add_parser("find", help="Find candidate YouTube home tours")
    find_cmd.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    find_cmd.add_argument("--backend", choices=["auto", "yt-dlp", "data-api"], default="auto")
    find_cmd.add_argument("--per-query", type=int, default=20, help="Results per query and pass")
    find_cmd.add_argument("--max-new", type=int, default=500, help="New videos to add this run")
    find_cmd.add_argument("--query", action="append", help="Run only these queries (repeatable)")

    args = parser.parse_args(argv)
    if args.command == "find":
        return _find(args)
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


def _backend(choice: str) -> Search:
    key = os.environ.get("YOUTUBE_API_KEY")
    if choice == "data-api" or (choice == "auto" and key):
        if not key:
            sys.exit("Set YOUTUBE_API_KEY to use the YouTube Data API backend.")
        return DataApiSearch(key)
    return YtDlpSearch()
