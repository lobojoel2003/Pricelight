# SPDX-License-Identifier: Apache-2.0
"""Discovery helpers: ``cms-hpt.txt`` files and CMS MRF file names.

Since January 2024 every hospital must host a ``cms-hpt.txt`` file at the
root of its website pointing to its machine-readable file(s)::

    location-name: Example Hospital
    source-page-url: https://example.org/price-transparency
    mrf-url: https://example.org/mrf/12-3456789_example-hospital_standardcharges.json
    contact-name: Jane Doe
    contact-email: jdoe@example.org

A file may list several locations separated by blank lines.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_KEYS = {
    "location-name": "location_name",
    "source-page-url": "source_page_url",
    "mrf-url": "mrf_url",
    "contact-name": "contact_name",
    "contact-email": "contact_email",
}


@dataclass(slots=True)
class HptEntry:
    location_name: str | None = None
    source_page_url: str | None = None
    mrf_url: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_hpt_txt(text: str) -> list[HptEntry]:
    """Parse the contents of a ``cms-hpt.txt`` file.

    Keys are case-insensitive. A new entry starts at a blank line or when a
    key repeats (some hospitals omit the blank separator line).
    """
    entries: list[HptEntry] = []
    current: dict[str, str] = {}

    def flush() -> None:
        if current:
            entries.append(HptEntry(**current))
            current.clear()

    for raw_line in text.lstrip("﻿").splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        attr = _KEYS.get(key.strip().lower().replace("_", "-").replace(" ", "-"))
        if attr is None:
            continue
        if attr in current:
            flush()
        current[attr] = value.strip()
    flush()
    return [e for e in entries if e.mrf_url or e.location_name]


def hpt_txt_url(website: str) -> str:
    """URL of the ``cms-hpt.txt`` file for a hospital website.

    >>> hpt_txt_url("example.org/about")
    'https://example.org/cms-hpt.txt'
    """
    if "://" not in website:
        website = "https://" + website
    parts = urlsplit(website)
    return urlunsplit((parts.scheme or "https", parts.netloc, "/cms-hpt.txt", "", ""))


_FILENAME_RE = re.compile(
    r"^(?P<ein>\d{2}-?\d{7})_(?P<name>.+?)_standardcharges\.(?P<ext>json|csv)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class MrfFileName:
    ein: str
    hospital_slug: str
    extension: str


def parse_mrf_filename(filename: str) -> MrfFileName | None:
    """Parse the CMS naming convention ``<ein>_<hospital-name>_standardcharges.<ext>``.

    >>> parse_mrf_filename("12-3456789_example-hospital_standardcharges.json")
    MrfFileName(ein='12-3456789', hospital_slug='example-hospital', extension='json')
    """
    base = filename.rsplit("/", 1)[-1]
    match = _FILENAME_RE.match(base)
    if match is None:
        return None
    ein = match.group("ein")
    if "-" not in ein:
        ein = f"{ein[:2]}-{ein[2:]}"
    return MrfFileName(
        ein=ein, hospital_slug=match.group("name"), extension=match.group("ext").lower()
    )
