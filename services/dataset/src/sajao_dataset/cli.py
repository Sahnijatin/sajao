"""Command line entry point: `python -m sajao_dataset find ...`."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

from sajao_dataset.download import (
    Segment,
    download_all,
    plan_head_segments,
    read_ledger,
    ytdlp_fetch,
)
from sajao_dataset.frames import fetch_yunet, sample_all, yunet_faces
from sajao_dataset.licenses import (
    DataApiVideos,
    append_licenses,
    apply_licenses,
    check_licenses,
    read_licenses,
)
from sajao_dataset.manifest import append_records, read_manifest
from sajao_dataset.prefilter import decide, read_decisions, write_decisions
from sajao_dataset.queries import ALL_QUERIES, QUERY_SET, category_of
from sajao_dataset.screen import (
    MAX_WINDOW_S,
    kept_segments,
    plan_screening,
    read_screening,
    run_screening,
    write_segments,
)
from sajao_dataset.youtube import DataApiSearch, Search, YtDlpSearch, find

DEFAULT_MANIFEST = Path("data/sources.jsonl")
DEFAULT_PREFILTER = Path("data/prefilter.jsonl")
DEFAULT_LICENSES = Path("data/licenses.jsonl")
DEFAULT_SCREENING = Path("data/screening.jsonl")
DEFAULT_SEGMENTS = Path("data/segments.jsonl")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sajao-dataset")
    commands = parser.add_subparsers(dest="command", required=True)

    find_cmd = commands.add_parser("find", help="Find candidate YouTube home tours")
    find_cmd.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    find_cmd.add_argument("--backend", choices=["auto", "yt-dlp", "data-api"], default="auto")
    find_cmd.add_argument("--per-query", type=int, default=20, help="Results per query and pass")
    find_cmd.add_argument("--max-new", type=int, default=500, help="New videos to add this run")
    find_cmd.add_argument("--query", action="append", help="Run only these queries (repeatable)")

    lic_cmd = commands.add_parser("licenses", help="Record each video's license (Data API)")
    lic_cmd.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    lic_cmd.add_argument("--licenses", type=Path, default=DEFAULT_LICENSES)
    lic_cmd.add_argument("--refresh", action="store_true", help="Recheck videos already recorded")

    pre_cmd = commands.add_parser("prefilter", help="Drop builder and designer promos")
    pre_cmd.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    pre_cmd.add_argument("--out", type=Path, default=DEFAULT_PREFILTER)

    sc_cmd = commands.add_parser("screen", help="Screen videos with Gemini on Vertex AI")
    sc_cmd.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    sc_cmd.add_argument("--prefilter", type=Path, default=DEFAULT_PREFILTER)
    sc_cmd.add_argument("--licenses", type=Path, default=DEFAULT_LICENSES)
    sc_cmd.add_argument("--ledger", type=Path, default=DEFAULT_SCREENING)
    sc_cmd.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS)
    sc_cmd.add_argument("--limit", type=int, default=50, help="Videos to screen this run")
    sc_cmd.add_argument("--cap-inr", type=float, default=500, help="Run spend cap in rupees")
    sc_cmd.add_argument("--concurrency", type=int, default=2)

    dl_cmd = commands.add_parser("download", help="Download kept segments (run on the PC)")
    dl_cmd.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    dl_cmd.add_argument("--prefilter", type=Path, default=DEFAULT_PREFILTER)
    dl_cmd.add_argument("--licenses", type=Path, default=DEFAULT_LICENSES)
    dl_cmd.add_argument("--segments", type=Path, help="Segments JSONL from screening")
    dl_cmd.add_argument("--clips", type=Path, default=Path("data/clips"))
    dl_cmd.add_argument("--ledger", type=Path, default=Path("data/downloads.jsonl"))
    dl_cmd.add_argument("--limit", type=int, default=50, help="Videos, when no --segments")
    dl_cmd.add_argument("--head-s", type=float, default=600, help="Head length without screening")
    dl_cmd.add_argument("--max-height", type=int, default=1080)
    dl_cmd.add_argument("--pause-s", type=float, default=5, help="Pause between segments")
    dl_cmd.add_argument("--cookies-from-browser", help="chrome, edge or firefox")
    dl_cmd.add_argument("--ffmpeg", help="Path to ffmpeg if it is not on PATH")

    fr_cmd = commands.add_parser(
        "frames", help="Sample frames, drop blur and duplicates, blur faces"
    )
    fr_cmd.add_argument("--clips", type=Path, default=Path("data/clips"))
    fr_cmd.add_argument("--ledger", type=Path, default=Path("data/downloads.jsonl"))
    fr_cmd.add_argument("--frames", type=Path, default=Path("data/frames"))
    fr_cmd.add_argument("--models", type=Path, default=Path("data/models"))
    fr_cmd.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable")

    ev_cmd = commands.add_parser("evalset", help="Build and score the Indian-home eval set")
    ev_cmd.add_argument(
        "stage", choices=["tag", "select", "label", "check", "export", "listing", "score"]
    )
    ev_cmd.add_argument("--frames-manifest", type=Path, default=Path("data/frames.jsonl"))
    ev_cmd.add_argument("--frames-dir", type=Path, default=Path("data/frames"))
    ev_cmd.add_argument("--folder", type=Path, default=Path("data/evalset"))
    ev_cmd.add_argument("--limit", type=int, default=None, help="At most this many frames")
    ev_cmd.add_argument("--total", type=int, default=200)
    ev_cmd.add_argument("--quota", type=int, default=20, help="Frames per target class")
    ev_cmd.add_argument("--concurrency", type=int, default=4)

    args = parser.parse_args(argv)
    if args.command == "evalset":
        return _evalset(args)
    if args.command == "frames":
        return _frames(args)
    if args.command == "download":
        return _download(args)
    if args.command == "find":
        return _find(args)
    if args.command == "prefilter":
        return _prefilter(args)
    if args.command == "licenses":
        return _licenses(args)
    if args.command == "screen":
        return _screen(args)
    return 2


def _evalset(args: argparse.Namespace) -> int:
    import json

    from sajao_dataset import evalset as ev
    from sajao_dataset import evalset_run as run

    folder: Path = args.folder
    selection_path = folder / "selection.json"

    def selected() -> list[dict[str, object]]:
        if not selection_path.exists():
            sys.exit("Run `evalset select` first.")
        frames: list[dict[str, object]] = json.loads(selection_path.read_text())["frames"]
        return frames[: args.limit] if args.limit else frames

    if args.stage == "select":
        tagged = ev.read_jsonl(folder / "tags.jsonl")
        pick = ev.select_stratified(tagged, total=args.total, quota=args.quota)
        selection_path.write_text(
            json.dumps(
                {
                    "version": ev.EVALSET_VERSION,
                    "frames": pick.frames,
                    "per_class": pick.per_class,
                    "short": pick.short,
                },
                indent=1,
                sort_keys=True,
            )
        )
        print(f"{len(pick.frames)} frames from {len(tagged)} tagged; per class {pick.per_class}")
        if pick.short:
            print(f"Target classes below the quota of {args.quota}: {pick.short}")
        return 0
    if args.stage == "export":
        frames, rows = run.export_handcheck(folder, args.frames_dir, selected())
        print(f"{rows} disagreements on {frames} frames: {folder / 'handcheck.jsonl'}")
        return 0
    if args.stage == "score":
        report = run.score(folder, selected())
        (folder / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True))
        print(json.dumps({k: v for k, v in report.items() if k != "per_class"}, indent=1))
        print(f"Report: {folder / 'report.json'}")
        return 0

    if not os.environ.get("GCP_PROJECT_ID"):
        sys.exit("Set GCP_PROJECT_ID and GCP_SA_KEY (and SAJAO_ANTHROPIC_API_KEY for Claude).")
    models = run.build_models(folder)
    if args.stage == "tag":
        pool = ev.pool_frames(ev.read_jsonl(args.frames_manifest))
        todo = pool[: args.limit] if args.limit else pool
        result = asyncio.run(
            run.run_stage(
                todo,
                folder / "tags.jsonl",
                run.tag_work(models, args.frames_dir),
                concurrency=args.concurrency,
            )
        )
    elif args.stage == "label":
        result = asyncio.run(
            run.run_stage(
                selected(),
                folder / "labels.jsonl",
                run.label_work(models, args.frames_dir),
                concurrency=args.concurrency,
            )
        )
    elif args.stage == "check":
        labels = {r["path"]: r["objects"] for r in ev.read_jsonl(folder / "labels.jsonl")}
        todo = [f for f in selected() if f["path"] in labels]
        result = asyncio.run(
            run.run_stage(
                todo,
                folder / "reviews.jsonl",
                run.check_work(models, args.frames_dir, labels),
                concurrency=args.concurrency,
            )
        )
    else:
        results = []
        for role in ("list", "cross_check"):
            results.append(
                asyncio.run(
                    run.run_stage(
                        selected(),
                        folder / f"listing_{role}.jsonl",
                        run.listing_work(models, args.frames_dir, role),
                        concurrency=args.concurrency,
                    )
                )
            )
        result = results[-1]
        print(f"lister: {results[0]}")
    print(
        f"{args.stage}: {result.done} done, {result.skipped} already done, {result.failed} failed;"
        f" answered by {result.by_model}" + (" (stopped at the spend cap)" if result.capped else "")
    )
    print(run.spend_line(models))
    return 0


def _find(args: argparse.Namespace) -> int:
    search = _backend(args.backend)
    existing = read_manifest(args.manifest)
    records = find(
        search,
        args.query or ALL_QUERIES,
        query_set=QUERY_SET if not args.query else "ad-hoc",
        category_of=category_of,
        seen={r.video_id for r in existing},
        per_query=args.per_query,
        max_new=args.max_new,
    )
    added = append_records(args.manifest, records)
    print(
        f"{added} new videos via {search.name} "
        f"(by category {dict(Counter(r.category for r in records))}); "
        f"{len(existing) + added} in {args.manifest}"
    )
    if os.environ.get("YOUTUBE_API_KEY"):
        ledger = args.manifest.parent / DEFAULT_LICENSES.name
        return _licenses(argparse.Namespace(manifest=args.manifest, licenses=ledger, refresh=False))
    print("Set YOUTUBE_API_KEY and run `licenses` to record each video's license.")
    return 0


def _licenses(args: argparse.Namespace) -> int:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        sys.exit("Set YOUTUBE_API_KEY to record licenses from the YouTube Data API.")
    sources = read_manifest(args.manifest)
    known = {} if args.refresh else read_licenses(args.licenses)
    todo = [s.video_id for s in sources if s.video_id not in known]
    records = check_licenses(DataApiVideos(key), todo)
    append_licenses(args.licenses, records)
    calls = -(-len(todo) // 50)
    print(
        f"{len(records)} videos checked ({calls} quota units): "
        f"{dict(Counter((r.license, r.availability) for r in records))}. Ledger: {args.licenses}"
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


def _screen(args: argparse.Namespace) -> int:
    project = os.environ.get("GCP_PROJECT_ID")
    if not project:
        sys.exit("Set GCP_PROJECT_ID (and GCP_SA_KEY, or sign in with gcloud ADC).")
    sources = apply_licenses(read_manifest(args.manifest), read_licenses(args.licenses))
    todo = plan_screening(
        sources, read_decisions(args.prefilter), read_screening(args.ledger), limit=args.limit
    )
    result = asyncio.run(
        run_screening(
            todo,
            project=project,
            ledger_path=args.ledger,
            cap_inr=args.cap_inr,
            call_log_path=args.ledger.parent / "screen_calls.jsonl",
            concurrency=args.concurrency,
        )
    )
    s = result.summary
    written = write_segments(args.segments, kept_segments(sources, read_screening(args.ledger)))
    print(
        f"{len(todo)} planned (first {MAX_WINDOW_S // 60} min each): {s.kept} kept, "
        f"{s.skipped} skipped, {s.failed} failed; answered by {s.by_model}; "
        f"billed Rs {result.billed_inr:.2f} of the Rs {args.cap_inr:g} cap"
        + (" (stopped at the cap)" if s.stopped_at_cap else "")
    )
    print(f"{written} segments in {args.segments}. Ledger: {args.ledger}")
    return 0


def _download(args: argparse.Namespace) -> int:
    if args.segments:
        with args.segments.open(encoding="utf-8") as f:
            segments = [Segment.model_validate_json(line) for line in f if line.strip()]
    else:
        sources = read_manifest(args.manifest)
        licenses = read_licenses(args.licenses)
        if not licenses:
            print("No license ledger yet; run `licenses` first to use Data API licenses.")
        segments = plan_head_segments(
            apply_licenses(sources, licenses),
            read_decisions(args.prefilter),
            head_s=args.head_s,
            limit=args.limit,
        )
    fetch = ytdlp_fetch(
        max_height=args.max_height,
        cookies_from_browser=args.cookies_from_browser,
        ffmpeg_location=args.ffmpeg,
    )
    summary = download_all(
        segments,
        clips_dir=args.clips,
        ledger_path=args.ledger,
        fetch=fetch,
        max_height=args.max_height,
        pause_s=args.pause_s,
    )
    print(
        f"{summary.downloaded} downloaded, {summary.skipped} already done, "
        f"{summary.failed} failed; {summary.bytes / 1e9:.2f} GB this run. Ledger: {args.ledger}"
    )
    return 1 if summary.failed else 0


def _frames(args: argparse.Namespace) -> int:
    faces = yunet_faces(fetch_yunet(args.models))
    summary = sample_all(
        read_ledger(args.ledger),
        clips_dir=args.clips,
        frames_dir=args.frames,
        frames_ledger=args.frames.parent / "frames.jsonl",
        done_ledger=args.frames.parent / "frames_done.jsonl",
        faces=faces,
        ffmpeg=args.ffmpeg,
    )
    print(
        f"{summary.clips} clips sampled, {summary.skipped} already done: "
        f"{summary.kept} of {summary.candidates} candidate frames kept, "
        f"{summary.faces_blurred} faces blurred; dropped {dict(summary.dropped)}"
    )
    return 0


def _backend(choice: str) -> Search:
    key = os.environ.get("YOUTUBE_API_KEY")
    if choice == "data-api" or (choice == "auto" and key):
        if not key:
            sys.exit("Set YOUTUBE_API_KEY to use the YouTube Data API backend.")
        return DataApiSearch(key)
    return YtDlpSearch()
