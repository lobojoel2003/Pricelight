# SPDX-License-Identifier: AGPL-3.0-or-later
"""``pricelight`` command line interface."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pricelight_parser import __version__ as parser_version

from . import demo
from .__about__ import __version__
from .build import build, publish
from .manifest import DataDir, read_manifest, write_manifest

DEFAULT_DATA = os.environ.get("PRICELIGHT_DATA", "data")


def _money(x: float | None) -> str:
    return "—" if x is None else f"${x:,.0f}" if x >= 100 else f"${x:,.2f}"


def _build_info() -> dict[str, Any]:
    """Build metadata from CI (GitHub Actions) or the environment."""
    info = {
        "version": os.environ.get("PRICELIGHT_VERSION", __version__),
        "build_number": os.environ.get("PRICELIGHT_BUILD_NUMBER")
        or os.environ.get("GITHUB_RUN_NUMBER"),
        "commit": (os.environ.get("PRICELIGHT_COMMIT") or os.environ.get("GITHUB_SHA") or "")[:12]
        or None,
    }
    return {k: v for k, v in info.items() if v}


def cmd_demo(args: argparse.Namespace) -> int:
    data = DataDir.at(args.data)
    entries = demo.generate(data, n=args.hospitals, seed=args.seed)
    print(f"wrote {len(entries)} synthetic hospital files and {data.manifest}")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    from .fetch import discover, make_client, merge_entries

    data = DataDir.at(args.data)
    existing = read_manifest(data.manifest) if data.manifest.is_file() else []
    found = []
    with make_client() as client:
        for site in args.websites:
            try:
                entries = discover(site, client)
            except Exception as exc:  # report and continue with other sites
                print(f"  {site}: {exc}", file=sys.stderr)
                continue
            print(f"  {site}: {len(entries)} location(s)")
            found.extend(entries)
    write_manifest(data.manifest, merge_entries(existing, found))
    print(f"manifest now lists {len(merge_entries(existing, []))} hospitals -> {data.manifest}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    from .fetch import fetch_one, make_client

    data = DataDir.at(args.data)
    entries = read_manifest(data.manifest)
    if args.only:
        entries = [e for e in entries if e.id in set(args.only)]
    failures = 0
    with make_client(timeout=args.timeout) as client:
        for entry in entries:
            result = fetch_one(entry, data, client)
            failures += result.status == "failed"
            detail = f"{result.bytes / 1e6:,.1f} MB" if result.bytes else result.message
            print(f"  {result.status:<12} {entry.id}  {detail}")
    return 1 if failures else 0


def cmd_geocode(args: argparse.Namespace) -> int:
    from .fetch import geocode_address, make_client

    data = DataDir.at(args.data)
    entries = read_manifest(data.manifest)
    changed = 0
    with make_client() as client:
        for entry in entries:
            if entry.lat is not None and entry.lon is not None and not args.force:
                continue
            if not entry.address:
                continue
            point = geocode_address(entry.address, client)
            if point:
                entry.lat, entry.lon = point
                changed += 1
            print(f"  {'ok' if point else 'no match':<9} {entry.id}")
    write_manifest(data.manifest, entries)
    print(f"geocoded {changed} hospital(s)")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from .ingest import ingest

    data = DataDir.at(args.data)
    started = time.perf_counter()

    def progress(outcome: Any, done: int, total: int) -> None:
        if args.quiet:
            return
        rows = outcome.record.get("rows") or 0
        extra = f"{rows:,} rows" if outcome.status in {"ok", "skipped"} else outcome.message
        print(f"  [{done:>4}/{total}] {outcome.status:<8} {outcome.hospital_id}  {extra}")

    frame = ingest(
        data, jobs=args.jobs, force=args.force, only=set(args.only or []) or None, progress=progress
    )
    ok = frame.filter(frame["status"] == "ok").height
    print(
        f"ingested {ok}/{frame.height} hospitals in {time.perf_counter() - started:.1f}s "
        f"-> {data.hospitals_table}"
    )
    return 0 if ok else 1


def cmd_build(args: argparse.Namespace) -> int:
    data = DataDir.at(args.data)
    summary = build(
        data,
        Path(args.out) if args.out else None,
        min_hospitals=args.min_hospitals,
        build_info=_build_info(),
    )
    print(f"built {summary}")
    if args.publish:
        publish(summary.out_dir, Path(args.publish))
        print(f"published to {args.publish}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """demo (optional) -> ingest -> build -> publish."""
    if args.demo:
        cmd_demo(args)
    args.only, args.force, args.quiet = None, False, True
    if cmd_ingest(args) != 0:
        return 1
    return cmd_build(args)


def cmd_report(args: argparse.Namespace) -> int:
    from .report import quality_report

    report = quality_report(DataDir.at(args.data))
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"hospitals in manifest   {report['hospitals']}")
    print(
        f"parsed / failed / missing  {report['parsed']} / {report['failed']} / {report['missing']}"
    )
    print(f"files with cash prices  {report['with_cash_prices']}")
    print(f"files with errors       {report['with_errors']}")
    print(f"attestation confirmed   {report['attested']}")
    print("formats:", ", ".join(f"{f['format']} ({f['len']})" for f in report["formats"]))
    print("most common issues:")
    for code, n in report["most_common_issues"]:
        print(f"  {n:>5} hospitals  {code}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    from .report import lookup

    site = Path(args.site) if args.site else DataDir.at(args.data).site
    service, rows = lookup(
        site, " ".join(args.service), state=args.state, payer=args.payer, limit=args.limit
    )
    if service is None:
        print("no matching service", file=sys.stderr)
        return 1
    print(
        f"{service['label']}  ({service['type']} {service['code']}) · {service['hospitals']} hospitals"
    )
    header = f"{'hospital':<44} {'state':<5} {'cash':>10} {'insurers (min–max)':>22}"
    if args.payer:
        header += f" {args.payer[:18]:>18}"
    print(header)
    for r in rows:
        line = f"{r['name'][:44]:<44} {r['state'] or '':<5} {_money(r['cash']):>10} "
        line += f"{_money(r['min']) + '–' + _money(r['max']):>22}"
        if args.payer:
            line += f" {_money(r['payer_rate']):>18}"
        print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="pricelight",
        description="Build a searchable hospital price dataset from CMS machine-readable files.",
    )
    ap.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__} (pricelight-parser {parser_version})",
    )
    ap.add_argument(
        "--data", default=DEFAULT_DATA, help="data directory (default: ./data or $PRICELIGHT_DATA)"
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("demo", help="generate a synthetic demo dataset (fictional hospitals)")
    p.add_argument("--hospitals", type=int, default=60)
    p.add_argument("--seed", type=int, default=20260101)
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("discover", help="read hospitals' cms-hpt.txt files into the manifest")
    p.add_argument("websites", nargs="+", help="hospital website(s), e.g. example.org")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("fetch", help="download machine-readable files listed in the manifest")
    p.add_argument("--only", nargs="*", help="hospital ids to fetch")
    p.add_argument("--timeout", type=float, default=120.0)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("geocode", help="fill missing coordinates (US Census geocoder)")
    p.add_argument("--force", action="store_true", help="re-geocode entries that have coordinates")
    p.set_defaults(func=cmd_geocode)

    p = sub.add_parser("ingest", help="parse downloaded files into the Parquet lake")
    p.add_argument("--jobs", type=int, default=None, help="parallel workers (default: CPUs, max 8)")
    p.add_argument("--force", action="store_true", help="re-parse unchanged files")
    p.add_argument("--only", nargs="*", help="hospital ids to ingest")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_ingest)

    def add_build_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--out", help="output directory (default: <data>/site)")
        p.add_argument("--publish", help="also copy the dataset here (e.g. site/public/data)")
        p.add_argument(
            "--min-hospitals", type=int, default=1, help="drop services offered by fewer hospitals"
        )

    p = sub.add_parser("build", help="build the web app dataset with DuckDB")
    add_build_args(p)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("run", help="ingest + build in one step (optionally generating demo data)")
    p.add_argument("--demo", action="store_true", help="generate the synthetic demo dataset first")
    p.add_argument("--hospitals", type=int, default=60)
    p.add_argument("--seed", type=int, default=20260101)
    p.add_argument("--jobs", type=int, default=None)
    add_build_args(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("report", help="data-quality summary of ingested files")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("query", help="look up a service's prices from the terminal")
    p.add_argument("service", nargs="+", help="code (70553) or words (mri brain)")
    p.add_argument("--state")
    p.add_argument("--payer")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--site", help="built dataset directory (default: <data>/site)")
    p.set_defaults(func=cmd_query)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s"
    )
    try:
        return int(args.func(args))
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"pricelight: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
