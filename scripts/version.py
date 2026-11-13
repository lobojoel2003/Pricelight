#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single-source versioning for every Pricelight component.

The version lives in ``VERSION`` and is mirrored into each package manifest:

    VERSION                                   0.1.0
    parser/src/pricelight_parser/__about__.py __version__ = "0.1.0"
    pipeline/src/pricelight/__about__.py      __version__ = "0.1.0"
    pipeline/pyproject.toml                   "pricelight-parser==0.1.0"
    site/package.json (+ package-lock.json)   "version": "0.1.0"
    pyproject.toml (workspace)                version = "0.1.0"

Usage:
    python scripts/version.py check [--tag v0.1.0]   verify everything agrees
    python scripts/version.py bump patch|minor|major|X.Y.Z
    python scripts/version.py notes [X.Y.Z]           print CHANGELOG section
    python scripts/version.py current
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?$"
)

ABOUT_FILES = (
    ROOT / "parser/src/pricelight_parser/__about__.py",
    ROOT / "pipeline/src/pricelight/__about__.py",
)
ABOUT_RE = re.compile(r'^__version__ = "([^"]+)"$', re.M)
PIN_RE = re.compile(r'"pricelight-parser==([^"]+)"')
WORKSPACE_RE = re.compile(r'^version = "([^"]+)"$', re.M)


def read_version() -> str:
    return (ROOT / "VERSION").read_text().strip()


def found_versions() -> dict[str, str | None]:
    found: dict[str, str | None] = {"VERSION": read_version()}
    for path in ABOUT_FILES:
        m = ABOUT_RE.search(path.read_text())
        found[str(path.relative_to(ROOT))] = m.group(1) if m else None
    m = PIN_RE.search((ROOT / "pipeline/pyproject.toml").read_text())
    found["pipeline/pyproject.toml (parser pin)"] = m.group(1) if m else None
    m = WORKSPACE_RE.search((ROOT / "pyproject.toml").read_text())
    found["pyproject.toml"] = m.group(1) if m else None
    pkg = json.loads((ROOT / "site/package.json").read_text())
    found["site/package.json"] = pkg.get("version")
    lock_path = ROOT / "site/package-lock.json"
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        found["site/package-lock.json"] = lock.get("version")
    return found


def cmd_check(args: argparse.Namespace) -> int:
    version = read_version()
    ok = True
    if not SEMVER.match(version):
        print(f"VERSION {version!r} is not semantic versioning (X.Y.Z[-pre])")
        ok = False
    for where, value in found_versions().items():
        mark = "ok " if value == version else "BAD"
        ok &= value == version
        print(f"  [{mark}] {where}: {value}")
    if args.tag:
        tag = args.tag.removeprefix("refs/tags/")
        if tag != f"v{version}":
            print(f"  [BAD] git tag {tag} does not match VERSION v{version}")
            ok = False
        else:
            print(f"  [ok ] git tag {tag}")
    changelog = (ROOT / "CHANGELOG.md").read_text()
    if f"## [{version}]" not in changelog:
        print(f"  [BAD] CHANGELOG.md has no '## [{version}]' section")
        ok = False
    else:
        print(f"  [ok ] CHANGELOG.md section {version}")
    print("versions agree" if ok else "version mismatch")
    return 0 if ok else 1


def next_version(current: str, part: str) -> str:
    if SEMVER.match(part):
        return part
    m = SEMVER.match(current)
    if not m:
        raise SystemExit(f"current version {current!r} is not semver")
    major, minor, patch = int(m["major"]), int(m["minor"]), int(m["patch"])
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}" if not m["pre"] else f"{major}.{minor}.{patch}"
    raise SystemExit(f"unknown bump {part!r}: use major, minor, patch or X.Y.Z")


def cmd_bump(args: argparse.Namespace) -> int:
    old = read_version()
    new = next_version(old, args.part)
    (ROOT / "VERSION").write_text(new + "\n")
    for path in ABOUT_FILES:
        path.write_text(ABOUT_RE.sub(f'__version__ = "{new}"', path.read_text()))
    pp = ROOT / "pipeline/pyproject.toml"
    pp.write_text(PIN_RE.sub(f'"pricelight-parser=={new}"', pp.read_text()))
    ws = ROOT / "pyproject.toml"
    ws.write_text(WORKSPACE_RE.sub(f'version = "{new}"', ws.read_text(), count=1))
    for name in ("package.json", "package-lock.json"):
        path = ROOT / "site" / name
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        data["version"] = new
        if name == "package-lock.json" and "" in data.get("packages", {}):
            data["packages"][""]["version"] = new
        path.write_text(json.dumps(data, indent=2) + "\n")
    changelog = ROOT / "CHANGELOG.md"
    text = changelog.read_text()
    today = dt.date.today().isoformat()
    if "## [Unreleased]" in text and f"## [{new}]" not in text:
        text = text.replace("## [Unreleased]", f"## [Unreleased]\n\n## [{new}] - {today}", 1)
        compare = f"[{new}]: https://github.com/lobojoel2003/Pricelight/compare/v{old}...v{new}"
        text = re.sub(
            r"^\[Unreleased\]: .*$",
            f"[Unreleased]: https://github.com/lobojoel2003/Pricelight/compare/v{new}...HEAD\n{compare}",
            text,
            count=1,
            flags=re.M,
        )
        changelog.write_text(text)
    print(f"{old} -> {new}")
    print(f"next: uv lock && git commit -am 'Release v{new}' && git tag -a v{new} -m 'v{new}'")
    return 0


def changelog_section(version: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text()
    m = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: |\Z)", text, re.M | re.S
    )
    if not m:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    return m.group(1).strip()


def cmd_notes(args: argparse.Namespace) -> int:
    print(changelog_section(args.version or read_version()))
    return 0


def cmd_current(_: argparse.Namespace) -> int:
    print(read_version())
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--tag")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("bump")
    p.add_argument("part")
    p.set_defaults(func=cmd_bump)
    p = sub.add_parser("notes")
    p.add_argument("version", nargs="?")
    p.set_defaults(func=cmd_notes)
    sub.add_parser("current").set_defaults(func=cmd_current)
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
