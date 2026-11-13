# SPDX-License-Identifier: AGPL-3.0-or-later
"""The hospital manifest and on-disk layout of a Pricelight data directory.

::

    data/
      manifest.csv                      one row per hospital (you edit this)
      raw/<hospital_id>/<file>          downloaded machine-readable files
      lake/charges/hospital_id=<id>/charges.parquet
      lake/hospitals.parquet            parse results, header, data quality
      site/                             compact dataset served to the web app
"""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

MANIFEST_COLUMNS = (
    "id",
    "name",
    "address",
    "city",
    "state",
    "zip",
    "lat",
    "lon",
    "website",
    "source_page_url",
    "mrf_url",
    "mrf_path",
    "ccn",
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


@dataclass(slots=True)
class HospitalEntry:
    id: str
    name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    lat: float | None = None
    lon: float | None = None
    website: str = ""
    source_page_url: str = ""
    mrf_url: str = ""
    mrf_path: str = ""
    ccn: str = ""

    def __post_init__(self) -> None:
        if not _ID_RE.match(self.id):
            raise ValueError(
                f"invalid hospital id {self.id!r}: use lowercase letters, digits and dashes"
            )
        self.state = self.state.upper()

    def to_row(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, value in asdict(self).items():
            out[key] = "" if value is None else str(value)
        return out


def slugify(text: str, max_len: int = 60) -> str:
    """
    >>> slugify("St. Example's Medical Center (Main)")
    'st-examples-medical-center-main'
    """
    text = text.lower().replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len].rstrip("-") or "hospital"


def _float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return float(value)


def read_manifest(path: str | Path) -> list[HospitalEntry]:
    path = Path(path)
    entries: list[HospitalEntry] = []
    seen: set[str] = set()
    names = {f.name for f in fields(HospitalEntry)}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for line, row in enumerate(csv.DictReader(fh), start=2):
            values = {
                k.strip(): (v or "").strip() for k, v in row.items() if k and k.strip() in names
            }
            if not values.get("id"):
                raise ValueError(f"{path}:{line}: missing id")
            kwargs: dict[str, Any] = dict(values)
            kwargs["lat"] = _float(values.get("lat"))
            kwargs["lon"] = _float(values.get("lon"))
            entry = HospitalEntry(**kwargs)
            if entry.id in seen:
                raise ValueError(f"{path}:{line}: duplicate id {entry.id!r}")
            seen.add(entry.id)
            entries.append(entry)
    return entries


def write_manifest(path: str | Path, entries: list[HospitalEntry]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry.to_row())
    tmp.replace(path)


@dataclass(frozen=True, slots=True)
class DataDir:
    root: Path

    @classmethod
    def at(cls, path: str | Path) -> DataDir:
        return cls(Path(path))

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.csv"

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def lake(self) -> Path:
        return self.root / "lake"

    @property
    def charges(self) -> Path:
        return self.lake / "charges"

    @property
    def hospitals_table(self) -> Path:
        return self.lake / "hospitals.parquet"

    @property
    def site(self) -> Path:
        return self.root / "site"

    def charges_file(self, hospital_id: str) -> Path:
        return self.charges / f"hospital_id={hospital_id}" / "charges.parquet"

    def raw_dir(self, hospital_id: str) -> Path:
        return self.raw / hospital_id

    def resolve_mrf(self, entry: HospitalEntry) -> Path | None:
        """Local file for a manifest entry: explicit ``mrf_path`` or the newest download."""
        if entry.mrf_path:
            p = Path(entry.mrf_path)
            return p if p.is_absolute() else (self.root / p)
        folder = self.raw_dir(entry.id)
        if not folder.is_dir():
            return None
        files = [p for p in folder.iterdir() if p.is_file() and not p.name.startswith((".", "_"))]
        files = [p for p in files if not p.name.endswith((".partial", ".json.meta"))]
        return max(files, key=lambda p: p.stat().st_mtime) if files else None
