# SPDX-License-Identifier: Apache-2.0
"""``pricelight-parse`` command line interface."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from . import __version__, open_mrf, parse_hpt_txt, to_parquet
from .base import BaseParser
from .models import Issue, Severity
from .sources import UnsupportedFileError


def _human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"  # pragma: no cover


def _print_issues(issues: Sequence[Issue], out: TextIO, limit: int = 30) -> None:
    if not issues:
        print("  no issues found", file=out)
        return
    for issue in issues[:limit]:
        mark = "x" if issue.severity is Severity.ERROR else "!"
        where = f"  (e.g. {', '.join(issue.examples[:3])})" if issue.examples else ""
        print(f"  [{mark}] {issue.code} x{issue.count:,}: {issue.message}{where}", file=out)
    if len(issues) > limit:
        print(f"  ... and {len(issues) - limit} more", file=out)


class _Progress:
    """Prints a throttled progress line to stderr while a file is parsed."""

    def __init__(self, parser: BaseParser, enabled: bool) -> None:
        self.parser = parser
        self.enabled = enabled and sys.stderr.isatty()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> _Progress:
        if self.enabled:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            sys.stderr.write("\r\033[K")

    def _run(self) -> None:
        start = time.monotonic()
        while not self._stop.wait(0.5):
            reader = self.parser.source.last_reader
            done = reader.count if reader else 0
            elapsed = time.monotonic() - start
            sys.stderr.write(
                f"\r  {self.parser.stats.rows:,} rows · {_human_bytes(done)} read · {elapsed:,.0f}s"
            )
            sys.stderr.flush()


def cmd_inspect(args: argparse.Namespace) -> int:
    parser = open_mrf(args.file, full_metadata=args.full_metadata)
    samples: list[dict[str, Any]] = []
    with _Progress(parser, not args.json):
        for row in parser.rows():
            if len(samples) < args.rows:
                samples.append(row.to_dict())
            if args.limit and parser.stats.rows >= args.limit:
                break
    info = parser.source.info
    if args.json:
        payload = {
            "file": str(info.path),
            "format": parser.format.value,
            "compression": info.compression,
            "header": parser.header.to_dict(),
            "stats": parser.stats.to_dict(),
            "issues": [i.to_dict() for i in parser.issues],
            "sample_rows": samples,
        }
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False, default=str)
        print()
        return 0
    h = parser.header
    s = parser.stats
    packing = info.compression or "uncompressed"
    print(f"{info.path.name}  ({_human_bytes(info.size_bytes)}, {packing})")
    print(f"  format          {parser.format.value}  (CMS template {h.version or '?'})")
    print(f"  hospital        {h.hospital_name or '?'}")
    if h.location_names:
        print(f"  locations       {'; '.join(h.location_names[:3])}")
    if h.addresses:
        print(f"  address         {h.addresses[0]}")
    print(f"  last updated    {h.last_updated_on or '?'}")
    print(f"  license         {h.license_number or '-'} ({h.license_state or '?'})")
    print(f"  attestation     {h.attestation_confirmed}")
    print(f"  items / rows    {s.items:,} / {s.rows:,}")
    print(f"  payer rows      {s.payer_rows:,} across {s.payers:,} payer names")
    print(f"  cash prices     {s.rows_with_cash:,} rows")
    for sample in samples:
        price = sample["negotiated_dollar"] or sample["discounted_cash"] or sample["gross_charge"]
        code = f"{sample['code_type'] or '?'} {sample['code'] or '?'}"
        description = str(sample["description"])[:48]
        print(f"    · {code}  {description:<48}  {sample['payer_name'] or '(item)'}  {price}")
    print("issues:")
    _print_issues(parser.issues, sys.stdout)
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    constants = {}
    if args.hospital_id:
        constants["hospital_id"] = args.hospital_id
    output = args.output or str(Path(args.file).with_suffix(".parquet"))
    started = time.perf_counter()
    result = to_parquet(
        args.file,
        output,
        constants=constants or None,
        compression=args.compression,
        full_metadata=args.full_metadata,
    )
    if args.meta:
        Path(args.meta).write_text(result.to_json(indent=2), encoding="utf-8")
    if not args.quiet:
        elapsed = time.perf_counter() - started
        print(
            f"wrote {result.stats.rows:,} rows from {result.source} ({result.format.value}) "
            f"to {output} in {elapsed:.1f}s; {len(result.issues)} issue types",
            file=sys.stderr,
        )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    parser = open_mrf(args.file, full_metadata=True)
    with _Progress(parser, not args.json):
        for _ in parser.rows():
            pass
    errors = [i for i in parser.issues if i.severity is Severity.ERROR]
    if args.json:
        json.dump(
            {
                "file": str(parser.source.path),
                "format": parser.format.value,
                "valid": not errors,
                "stats": parser.stats.to_dict(),
                "issues": [i.to_dict() for i in parser.issues],
            },
            sys.stdout,
            indent=2,
        )
        print()
    else:
        verdict = "no blocking problems" if not errors else f"{len(errors)} error type(s)"
        print(f"{parser.source.display_name}: {parser.format.value}, {verdict}")
        _print_issues(parser.issues, sys.stdout, limit=100)
        print(
            "\nNote: this is a lightweight check, not the official CMS validator "
            "(https://cmsgov.github.io/hpt-tool/)."
        )
    return 1 if errors else 0


def cmd_hpt_txt(args: argparse.Namespace) -> int:
    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text("utf-8-sig")
    entries = [e.to_dict() for e in parse_hpt_txt(text)]
    json.dump(entries, sys.stdout, indent=2)
    print()
    return 0 if entries else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="pricelight-parse",
        description="Stream hospital price transparency files (CMS JSON / CSV tall / CSV wide).",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="summarize a file and show sample rows")
    p.add_argument("file")
    p.add_argument("--rows", type=int, default=5, help="sample rows to show (default 5)")
    p.add_argument("--limit", type=int, default=0, help="stop after N rows (0 = whole file)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--full-metadata", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("convert", help="convert a file to Parquet")
    p.add_argument("file")
    p.add_argument("-o", "--output", help="output .parquet path (default: next to input)")
    p.add_argument("--hospital-id", help="add a constant hospital_id column")
    p.add_argument("--meta", help="also write the parse summary as JSON to this path")
    p.add_argument("--compression", default="zstd", help="parquet codec (default zstd)")
    p.add_argument(
        "--full-metadata", action="store_true", help="always read trailing JSON metadata"
    )
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("validate", help="report data-quality issues; exit 1 on errors")
    p.add_argument("file")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("hpt-txt", help="parse a cms-hpt.txt discovery file ('-' for stdin)")
    p.add_argument("file")
    p.set_defaults(func=cmd_hpt_txt)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (UnsupportedFileError, FileNotFoundError) as exc:
        print(f"pricelight-parse: error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover - interactive
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
