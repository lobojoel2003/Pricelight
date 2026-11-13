# SPDX-License-Identifier: AGPL-3.0-or-later
"""Discovery (``cms-hpt.txt``), downloads and geocoding.

Downloads stream to disk in 1 MiB chunks (files are often several GB),
use conditional requests (ETag / Last-Modified) so unchanged files are not
fetched again, and retry transient failures with exponential backoff.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

from pricelight_parser import hpt_txt_url, parse_hpt_txt

from .__about__ import __version__
from .manifest import DataDir, HospitalEntry, slugify

log = logging.getLogger(__name__)

USER_AGENT = f"Pricelight/{__version__} (+https://github.com/lobojoel2003/Pricelight)"
FETCH_STATE = "_fetch.json"
RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def make_client(
    transport: httpx.BaseTransport | None = None, timeout: float = 60.0
) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(timeout, connect=20.0),
        transport=transport,
    )


def _with_retries(fn: Callable[[], httpx.Response], attempts: int = 4) -> httpx.Response:
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            response = fn()
        except httpx.TransportError:
            if attempt == attempts:
                raise
        else:
            if response.status_code not in RETRY_STATUS or attempt == attempts:
                return response
            response.close()
        time.sleep(delay)
        delay *= 2
    raise AssertionError("unreachable")  # pragma: no cover


# -- discovery ---------------------------------------------------------------


def discover(website: str, client: httpx.Client) -> list[HospitalEntry]:
    """Read a hospital website's ``cms-hpt.txt`` and return manifest entries."""
    url = hpt_txt_url(website)
    response = _with_retries(lambda: client.get(url))
    response.raise_for_status()
    entries = []
    for hpt in parse_hpt_txt(response.text):
        name = hpt.location_name or urlsplit(url).netloc
        entries.append(
            HospitalEntry(
                id=slugify(name),
                name=name,
                website=website,
                source_page_url=hpt.source_page_url or "",
                mrf_url=hpt.mrf_url or "",
            )
        )
    return entries


def merge_entries(
    existing: list[HospitalEntry], found: Iterable[HospitalEntry]
) -> list[HospitalEntry]:
    """Add discovered entries to a manifest, updating URLs of known ids."""
    by_id = {e.id: e for e in existing}
    merged = list(existing)
    for entry in found:
        current = by_id.get(entry.id)
        if current is None:
            merged.append(entry)
            by_id[entry.id] = entry
            continue
        current.mrf_url = entry.mrf_url or current.mrf_url
        current.source_page_url = entry.source_page_url or current.source_page_url
        current.website = entry.website or current.website
    return merged


# -- downloads -----------------------------------------------------------------


@dataclass(slots=True)
class FetchResult:
    hospital_id: str
    status: str  # downloaded | not-modified | failed | skipped
    path: Path | None = None
    bytes: int = 0
    message: str = ""


def _filename_for(url: str, response: httpx.Response) -> str:
    disposition = response.headers.get("content-disposition", "")
    if "filename=" in disposition:
        name = disposition.split("filename=", 1)[1].strip("\"'; ")
        if name:
            return Path(name).name
    name = Path(unquote(urlsplit(str(response.url) or url).path)).name
    return name or "mrf.dat"


def fetch_one(entry: HospitalEntry, data: DataDir, client: httpx.Client) -> FetchResult:
    if not entry.mrf_url:
        return FetchResult(entry.id, "skipped", message="no mrf_url")
    folder = data.raw_dir(entry.id)
    folder.mkdir(parents=True, exist_ok=True)
    state_path = folder / FETCH_STATE
    state = json.loads(state_path.read_text("utf-8")) if state_path.is_file() else {}
    headers = {}
    if (
        state.get("url") == entry.mrf_url
        and state.get("file")
        and (folder / state["file"]).is_file()
    ):
        if state.get("etag"):
            headers["If-None-Match"] = state["etag"]
        if state.get("last_modified"):
            headers["If-Modified-Since"] = state["last_modified"]

    def request() -> httpx.Response:
        req = client.build_request("GET", entry.mrf_url, headers=headers)
        return client.send(req, stream=True)

    try:
        response = _with_retries(request)
    except httpx.HTTPError as exc:
        return FetchResult(entry.id, "failed", message=str(exc))
    try:
        if response.status_code == 304:
            return FetchResult(entry.id, "not-modified", folder / state["file"])
        if response.status_code >= 400:
            return FetchResult(entry.id, "failed", message=f"HTTP {response.status_code}")
        name = _filename_for(entry.mrf_url, response)
        target = folder / name
        partial = folder / (name + ".partial")
        digest = hashlib.sha256()
        size = 0
        with partial.open("wb") as fh:
            for chunk in response.iter_bytes(1 << 20):
                fh.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        for old in folder.iterdir():
            if old.is_file() and old.name not in {partial.name, FETCH_STATE}:
                old.unlink()
        partial.replace(target)
        state = {
            "url": entry.mrf_url,
            "final_url": str(response.url),
            "file": name,
            "bytes": size,
            "sha256": digest.hexdigest(),
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        state_path.write_text(json.dumps(state, indent=2), "utf-8")
    finally:
        response.close()
    return FetchResult(entry.id, "downloaded", target, size)


# -- geocoding ---------------------------------------------------------------

CENSUS_GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


def geocode_address(address: str, client: httpx.Client) -> tuple[float, float] | None:
    """Geocode a US street address with the free US Census Bureau geocoder."""
    response = _with_retries(
        lambda: client.get(
            CENSUS_GEOCODER,
            params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
        )
    )
    if response.status_code != 200:
        return None
    matches = response.json().get("result", {}).get("addressMatches") or []
    if not matches:
        return None
    coords = matches[0]["coordinates"]
    return round(float(coords["y"]), 5), round(float(coords["x"]), 5)
