# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pricelight.catalog import BY_KEY, SERVICES, category_for
from pricelight.fetch import discover, fetch_one, geocode_address, make_client, merge_entries
from pricelight.manifest import DataDir, HospitalEntry, read_manifest, slugify, write_manifest
from pricelight.payers import clean_payer_name, normalize_payer


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AETNA", "Aetna"),
        ("Aetna Better Health of Texas", "Aetna"),
        ("CIGNA HEALTHCARE", "Cigna"),
        ("UHC", "UnitedHealthcare"),
        ("United Healthcare Community Plan", "UnitedHealthcare"),
        ("BCBS of Illinois", "Blue Cross Blue Shield"),
        ("Anthem Blue Cross", "Anthem"),
        ("MEDICARE", "Medicare"),
        ("Medicare Advantage - Acme", "Medicare Advantage (other)"),
        ("NORTHWIND HEALTH INC", "Northwind Health"),
        ("Evergreen Shield, LLC", "Evergreen Shield"),
        ("REGIONAL CARE NETWORK, LLC", "Regional Care Network"),
        ("ACME HEALTH PLAN OF THE OZARKS", "Acme Health Plan of the Ozarks"),
        ("  ", None),
        (None, None),
    ],
)
def test_normalize_payer(raw: str | None, expected: str | None) -> None:
    assert normalize_payer(raw) == expected


def test_clean_payer_keeps_acronyms() -> None:
    assert clean_payer_name("ACME PPO HMO") == "Acme PPO HMO"
    assert clean_payer_name("Acme  Co.") == "Acme"


def test_catalog() -> None:
    keys = [s.key for s in SERVICES]
    assert len(keys) == len(set(keys))
    assert BY_KEY["MS-DRG:470"].category == "Hospital stays"
    assert all(s.base > 0 for s in SERVICES)
    assert category_for("CPT", "71250") == "Imaging"
    assert category_for("CPT", "85610") == "Lab tests"
    assert category_for("CPT", "27447") == "Procedures & surgery"
    assert category_for("CPT", "99214") == "Visits & therapy"
    assert category_for("APR-DRG", "560") == "Hospital stays"
    assert category_for("HCPCS", "J1885") == "Drugs"
    assert category_for("HCPCS", "A0428") == "Other services"


def test_manifest_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "m.csv"
    entries = [
        HospitalEntry(id="a-1", name="A", state="tx", lat=1.5, lon=-2.25),
        HospitalEntry(id="b", name="B, Inc"),
    ]
    write_manifest(path, entries)
    back = read_manifest(path)
    assert back[0].state == "TX"
    assert back[0].lat == 1.5
    assert back[1].lat is None
    assert back[1].name == "B, Inc"
    path.write_text("id,name\nx,1\nx,2\n")
    with pytest.raises(ValueError, match="duplicate"):
        read_manifest(path)
    path.write_text("id,name\n,1\n")
    with pytest.raises(ValueError, match="missing id"):
        read_manifest(path)
    with pytest.raises(ValueError, match="invalid hospital id"):
        HospitalEntry(id="Bad Id")
    assert slugify("  !!!  ") == "hospital"


HPT = """location-name: Example North
source-page-url: https://example.org/prices
mrf-url: https://example.org/files/99-1234567_example-north_standardcharges.json

location-name: Example South
mrf-url: https://example.org/files/south.csv
"""


def _transport(calls: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/cms-hpt.txt":
            return httpx.Response(200, text=HPT)
        if request.url.path.endswith(".json"):
            if request.headers.get("if-none-match") == '"v1"':
                return httpx.Response(304)
            return httpx.Response(200, content=b'{"hospital_name": "x"}', headers={"ETag": '"v1"'})
        if request.url.path.endswith("south.csv"):
            return httpx.Response(404)
        if "geocoder" in request.url.path:
            if "Nowhere" in str(request.url):
                return httpx.Response(200, json={"result": {"addressMatches": []}})
            return httpx.Response(
                200,
                json={"result": {"addressMatches": [{"coordinates": {"x": -97.74, "y": 30.27}}]}},
            )
        return httpx.Response(500)

    return httpx.MockTransport(handler)


def test_discover_fetch_geocode(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    client = make_client(transport=_transport(calls))
    found = discover("example.org", client)
    assert [e.id for e in found] == ["example-north", "example-south"]
    assert found[0].source_page_url == "https://example.org/prices"
    assert calls[0].headers["user-agent"].startswith("Pricelight/")

    existing = [HospitalEntry(id="example-north", name="Example North", city="Austin")]
    merged = merge_entries(existing, found)
    assert len(merged) == 2
    assert merged[0].city == "Austin"
    assert merged[0].mrf_url.endswith(".json")

    data = DataDir.at(tmp_path)
    first = fetch_one(merged[0], data, client)
    assert first.status == "downloaded"
    assert first.path is not None
    assert first.path.name == "99-1234567_example-north_standardcharges.json"
    state = json.loads((data.raw_dir("example-north") / "_fetch.json").read_text())
    assert state["etag"] == '"v1"'
    assert data.resolve_mrf(merged[0]) == first.path

    second = fetch_one(merged[0], data, client)
    assert second.status == "not-modified"
    assert fetch_one(merged[1], data, client).status == "failed"
    assert fetch_one(HospitalEntry(id="none"), data, client).status == "skipped"

    assert geocode_address("1 Main St, Austin, TX", client) == (30.27, -97.74)
    assert geocode_address("Nowhere", client) is None
