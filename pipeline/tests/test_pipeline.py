# SPDX-License-Identifier: AGPL-3.0-or-later
"""End-to-end: synthetic files -> ingest -> DuckDB build -> site dataset."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import polars as pl
import pytest

from pricelight import demo
from pricelight.build import build, publish
from pricelight.cli import main
from pricelight.ingest import ingest
from pricelight.manifest import DataDir, read_manifest, write_manifest
from pricelight.report import lookup, quality_report


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> DataDir:
    data = DataDir.at(tmp_path_factory.mktemp("data"))
    demo.generate(data, n=20, seed=7)
    ingest(data, jobs=2)
    build(data, build_info={"version": "test", "build_number": "42"})
    return data


def test_demo_covers_every_layout(tmp_path: Path) -> None:
    hospitals = demo.plan_hospitals(20, seed=7)
    layouts = {h.layout for h in hospitals}
    assert layouts == {"json-v3", "csv-tall-v3", "csv-wide-v3", "json-v2", "csv-tall-v2"}
    assert {h.compression for h in hospitals} >= {None, "gzip"}
    # deterministic
    again = demo.plan_hospitals(20, seed=7)
    assert [h.entry.id for h in hospitals] == [h.entry.id for h in again]
    name, payload = demo.render(hospitals[0], seed=7)
    name2, payload2 = demo.render(again[0], seed=7)
    assert (name, payload) == (name2, payload2)


def test_ingest_writes_lake(built: DataDir) -> None:
    hospitals = pl.read_parquet(built.hospitals_table)
    assert hospitals.height == 20
    assert set(hospitals["status"]) == {"ok"}
    assert set(hospitals["format"]) == {"json", "csv-tall", "csv-wide"}
    assert hospitals["rows"].min() > 100
    for hid in hospitals["id"]:
        assert built.charges_file(hid).is_file()
    con = duckdb.connect()
    (n,) = con.sql(
        f"SELECT count(DISTINCT hospital_id) FROM read_parquet('{built.charges.as_posix()}/*/*.parquet', hive_partitioning=true)"
    ).fetchall()[0]
    assert n == 20


def test_ingest_is_incremental(built: DataDir) -> None:
    seen = []
    ingest(built, jobs=1, progress=lambda o, *_: seen.append(o.status))
    assert set(seen) == {"skipped"}
    first = read_manifest(built.manifest)[0]
    seen.clear()
    ingest(built, jobs=1, only={first.id}, force=True, progress=lambda o, *_: seen.append(o.status))
    assert seen == ["ok"]
    assert pl.read_parquet(built.hospitals_table).height == 20  # partial run keeps the rest


def test_site_dataset(built: DataDir) -> None:
    site = built.site
    meta = json.loads((site / "meta.json").read_text())
    assert meta["demo"] is True
    assert meta["counts"]["hospitals"] == 20
    assert meta["build"] == {"version": "test", "build_number": "42"}

    services = json.loads((site / "services.json").read_text())
    ids = {s["id"] for s in services}
    assert {"CPT:70553", "MS-DRG:470", "HCPCS:G0121"} <= ids
    mri = next(s for s in services if s["id"] == "CPT:70553")
    assert mri["label"].startswith("MRI of the brain")
    assert mri["category"] == "Imaging"
    assert mri["cash"]["min"] <= mri["cash"]["median"] <= mri["cash"]["max"]
    assert not any(s["type"] == "CDM" for s in services)

    payers = json.loads((site / "payers.json").read_text())
    names = {p["name"] for p in payers}
    # spelling variants such as "NORTHWIND HEALTH INC" fold into one payer
    assert "Northwind Health" in names
    assert not any(n.isupper() for n in names)
    assert len(names) <= len(demo.PAYERS)

    hospitals = json.loads((site / "hospitals.json").read_text())
    assert all(h["lat"] and h["lon"] for h in hospitals)
    assert all(h["file"]["format"] in {"json", "csv-tall", "csv-wide"} for h in hospitals)

    con = duckdb.connect()
    prices = con.sql(f"SELECT * FROM read_parquet('{(site / 'prices.parquet').as_posix()}')").pl()
    assert set(prices["service"].unique()) == ids
    items = prices.filter(pl.col("payer").is_null())
    # exactly one item row per service x hospital
    assert items.height == items.select("service", "hospital").unique().height
    payer_rows = prices.filter(pl.col("payer").is_not_null())
    assert payer_rows["rate"].null_count() == 0
    assert set(payer_rows["rate_basis"].unique()) <= {"dollar", "allowed"}
    # DRGs resolve to the inpatient setting
    assert set(items.filter(pl.col("service") == "MS-DRG:470")["setting"]) == {"inpatient"}
    # sorted by service for range-request friendly row groups
    assert prices["service"].to_list() == sorted(prices["service"].to_list())


def test_lookup_and_report(built: DataDir) -> None:
    service, rows = lookup(built.site, "70553")
    assert service is not None
    assert service["id"] == "CPT:70553"
    cash = [r["cash"] for r in rows if r["cash"] is not None]
    assert cash == sorted(cash)
    service, rows = lookup(built.site, "knee replacement", payer="Northwind Health", limit=3)
    assert service["id"] == "MS-DRG:470"
    assert len(rows) <= 3
    assert all(r["payer_rate"] for r in rows)
    assert lookup(built.site, "zzzz not a service") == (None, [])

    report = quality_report(built)
    assert report["parsed"] == 20
    assert report["hospitals"] == 20


def test_publish(built: DataDir, tmp_path: Path) -> None:
    publish(built.site, tmp_path / "public")
    assert sorted(p.name for p in (tmp_path / "public").iterdir()) == [
        "hospitals.json",
        "meta.json",
        "payers.json",
        "prices.parquet",
        "services.json",
    ]


def test_failed_and_missing_files(tmp_path: Path) -> None:
    data = DataDir.at(tmp_path)
    demo.generate(data, n=3, seed=1)
    entries = read_manifest(data.manifest)
    broken = data.root / "broken.csv"
    broken.write_text("not,a,cms\nfile,at,all\n")
    entries[1].mrf_path = "broken.csv"
    entries[2].mrf_path = "does-not-exist.json"
    write_manifest(data.manifest, entries)
    frame = ingest(data, jobs=1)
    assert frame["status"].to_list() == ["ok", "failed", "missing"]
    summary = build(data)
    assert summary.hospitals == 1


def test_orphan_partitions_removed(tmp_path: Path) -> None:
    data = DataDir.at(tmp_path)
    demo.generate(data, n=3, seed=3)
    ingest(data, jobs=1)
    entries = read_manifest(data.manifest)
    write_manifest(data.manifest, entries[:2])
    ingest(data, jobs=1)
    assert not data.charges_file(entries[2].id).exists()


def test_cli_run_and_query(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = str(tmp_path / "d")
    public = tmp_path / "public"
    assert (
        main(
            [
                "--data",
                data,
                "run",
                "--demo",
                "--hospitals",
                "6",
                "--jobs",
                "1",
                "--publish",
                str(public),
            ]
        )
        == 0
    )
    assert (public / "prices.parquet").is_file()
    assert main(["--data", data, "query", "lipid", "panel"]) == 0
    out = capsys.readouterr().out
    assert "Lipid panel" in out
    assert main(["--data", data, "report", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["parsed"] == 6
    assert main(["--data", data, "query", "qqqq"]) == 1
    assert main(["--data", str(tmp_path / "empty"), "build"]) == 2
