# SPDX-License-Identifier: Apache-2.0
"""End-to-end parsing of each CMS layout and template version."""

from __future__ import annotations

import bz2
import gzip
import json
import lzma
import zipfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from pricelight_parser import (
    CHARGE_SCHEMA,
    MRFFormat,
    UnsupportedFileError,
    open_mrf,
    read_result_metadata,
    record_batch_reader,
    to_parquet,
)


def issue_codes(parser) -> set[str]:
    return {i.code for i in parser.issues}


def test_json_v3(fixtures: Path) -> None:
    mrf = open_mrf(fixtures / "v3.json")
    assert mrf.format is MRFFormat.JSON
    # metadata is available right after open (pre-scan), before iterating
    assert mrf.header.hospital_name == "Example Lake Hospital"
    rows = list(mrf.rows())
    h = mrf.header
    assert h.version == "3.0.0"
    assert h.license_state == "WI"
    assert h.attestation_confirmed is True
    assert h.attester_name == "Lee Placeholder"
    assert h.type_2_npis == ["1234567927"]
    assert mrf.stats.items == 3
    assert len(rows) == 7

    ct = [r for r in rows if r.code == "74177"]
    assert {r.payer_name for r in ct} == {
        "Northwind Health",
        "Summit Mutual",
        "Harbor Health Plan",
        "Keystone Care",
    }
    assert all(r.code_type == "CPT" for r in ct)
    assert ct[0].codes[1].type == "CDM"
    assert ct[0].discounted_cash == 2100
    keystone = next(r for r in ct if r.payer_name == "Keystone Care")
    assert keystone.negotiated_dollar is None
    assert keystone.negotiated_percentage == 55
    assert keystone.median_amount == 2210
    assert keystone.p10_amount == 1800
    assert keystone.p90_amount == 2900
    assert keystone.allowed_count == "34"
    assert keystone.best_payer_amount == 2210

    drg = [r for r in rows if r.code_type == "MS-DRG"]
    assert drg[0].code == "807"  # "0807" + "MSDRG" normalized
    assert drg[0].setting == "inpatient"

    drug = next(r for r in rows if r.code_type == "NDC")
    assert drug.payer_name is None
    assert drug.drug_unit == 1
    assert drug.drug_type == "EA"

    # modifier_information trails the charge array; it is read on request
    assert mrf.header.modifier_information == []
    full = open_mrf(fixtures / "v3.json", full_metadata=True)
    list(full.rows())
    assert len(full.header.modifier_information) == 1
    assert {"nonstandard-code-type", "other-methodology-without-notes"} <= issue_codes(mrf)


def test_json_v2_with_trailing_metadata(fixtures: Path) -> None:
    """v2 aliases (affirmation, hospital_location, estimated_amount) and
    metadata placed *after* the charge array."""
    mrf = open_mrf(fixtures / "v2.json")
    rows = list(mrf.rows())
    h = mrf.header
    assert h.hospital_name == "Example Coast Hospital"
    assert h.location_names == ["Example Coast Hospital"]
    assert h.attestation_confirmed is True
    assert h.version == "2.0.0"
    assert len(rows) == 2
    assert rows[0].estimated_amount == 158.5
    assert rows[0].modifiers == ["25"]
    assert rows[1].methodology == "fee schedule"  # "fee_schedule" normalized
    assert "missing-hospital-name" not in issue_codes(mrf)
    # v3-only requirements are not enforced on v2 files
    assert "missing-type-2-npi" not in issue_codes(mrf)


def test_csv_tall_v3(fixtures: Path) -> None:
    mrf = open_mrf(fixtures / "v3_tall.csv")
    assert mrf.format is MRFFormat.CSV_TALL
    rows = list(mrf.rows())
    h = mrf.header
    assert h.hospital_name == "Example Valley Hospital"
    assert h.location_names == ["Example Valley Hospital", "Example Valley Clinic"]
    assert len(h.addresses) == 2
    assert h.license_number == "OR-5521"
    assert h.license_state == "OR"
    assert h.type_2_npis == ["1234567893", "1234567901"]
    assert h.attestation_confirmed is True
    assert h.attester_name == "Pat Example"
    assert len(rows) == 8

    mri = [r for r in rows if r.code == "70553"]
    assert len(mri) == 4
    assert mri[0].gross_charge == 4200
    assert mri[0].min_negotiated == 980
    keystone = next(r for r in mri if r.payer_name == "Keystone Care")
    assert keystone.negotiated_percentage == 62.5
    assert keystone.allowed_count == "1 through 10"
    assert keystone.methodology == "percent of total billed charges"

    drug = next(r for r in rows if r.code_type == "HCPCS")
    assert drug.payer_name is None
    assert drug.codes[1].type == "NDC"
    assert drug.additional_generic_notes == "Cash price applies to self-pay patients"

    room = next(r for r in rows if r.code_type == "RC")
    assert room.code == "0120"
    assert room.negotiated_algorithm.startswith("Per diem")
    assert room.methodology == "per diem"
    assert not any(i.severity.value == "error" for i in mrf.issues)


def test_csv_wide_v3(fixtures: Path) -> None:
    mrf = open_mrf(fixtures / "v3_wide.csv")
    assert mrf.format is MRFFormat.CSV_WIDE
    rows = list(mrf.rows())
    assert mrf.header.last_updated_on == "2026-02-15"  # MM/DD/YYYY accepted
    assert mrf.header.license_state == "WA"
    colonoscopy = [r for r in rows if r.code == "45378"]
    assert [(r.payer_name, r.plan_name, r.negotiated_dollar) for r in colonoscopy] == [
        ("Northwind Health", "PPO", 1320.0),
        ("Summit Mutual", "HMO Select", 1710.0),
    ]
    bmp = [r for r in rows if r.code == "80048"]
    assert len(bmp) == 1 and bmp[0].payer_name == "Summit Mutual"
    xray = [r for r in rows if r.code == "71046"]
    assert len(xray) == 1 and xray[0].payer_name is None
    assert xray[0].modifiers == ["26"]
    assert xray[0].additional_generic_notes == "No payer contracts"
    assert mrf.issues == []


def test_messy_csv(fixtures: Path) -> None:
    """cp1252 text, padded headers, '$1,020.00', N/A, abbreviations, CRLF."""
    mrf = open_mrf(fixtures / "messy_v2_tall.csv")
    rows = list(mrf.rows())
    assert mrf.header.hospital_name == "Example Prairie Hospital – Main Campus"
    assert mrf.header.last_updated_on == "2025-07-01"
    assert mrf.header.license_state == "TX"
    assert mrf.header.license_number is None
    assert rows[0].gross_charge == 1020.0
    assert rows[0].discounted_cash is None
    assert rows[0].negotiated_dollar == 31.2
    assert rows[0].setting == "outpatient"
    assert rows[0].code_type == "CPT"
    assert rows[1].payer_name is None
    assert rows[2].gross_charge is None
    codes = issue_codes(mrf)
    assert {"formatted-number", "nonstandard-setting", "non-numeric-value"} <= codes
    assert "payer-without-charge" in codes


@pytest.mark.parametrize("kind", ["gzip", "zip", "bz2", "xz"])
def test_compressed_inputs(fixtures: Path, tmp_path: Path, kind: str) -> None:
    raw = (fixtures / "v3.json").read_bytes()
    # deliberately misleading extension: detection uses magic bytes
    path = tmp_path / "hospital.data"
    if kind == "gzip":
        path.write_bytes(gzip.compress(raw))
    elif kind == "bz2":
        path.write_bytes(bz2.compress(raw))
    elif kind == "xz":
        path.write_bytes(lzma.compress(raw))
    else:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("README.txt", "read me")
            zf.writestr("__MACOSX/._x.json", "junk")
            zf.writestr("12-3456789_example_standardcharges.json", raw)
    mrf = open_mrf(path)
    assert mrf.source.compression == kind
    assert len(list(mrf.rows())) == 7
    assert mrf.header.hospital_name == "Example Lake Hospital"


def test_utf8_bom_csv(fixtures: Path, tmp_path: Path) -> None:
    path = tmp_path / "bom.csv"
    path.write_bytes(b"\xef\xbb\xbf" + (fixtures / "v3_wide.csv").read_bytes())
    mrf = open_mrf(path)
    assert mrf.format is MRFFormat.CSV_WIDE
    list(mrf.rows())
    assert mrf.header.hospital_name == "Example Ridge Medical Center"


def test_to_parquet_roundtrip(fixtures: Path, tmp_path: Path) -> None:
    out = tmp_path / "out" / "v3.parquet"
    result = to_parquet(fixtures / "v3.json", out, constants={"hospital_id": "lake"})
    assert result.ok
    assert out.exists()
    assert not out.with_name(out.name + ".partial").exists()
    table = pq.read_table(out)
    assert table.num_rows == 7
    assert table.schema.names == [*CHARGE_SCHEMA.names, "hospital_id"]
    assert set(table.column("hospital_id").to_pylist()) == {"lake"}
    codes = table.column("codes").to_pylist()[0]
    assert codes == [{"code": "74177", "type": "CPT"}, {"code": "3500123", "type": "CDM"}]
    meta = read_result_metadata(out)
    assert meta is not None
    assert meta["header"]["hospital_name"] == "Example Lake Hospital"
    assert meta["stats"]["rows"] == 7
    assert meta["format"] == "json"
    json.dumps(meta)  # serializable


def test_empty_charges_still_writes_schema(tmp_path: Path) -> None:
    src = tmp_path / "empty.json"
    src.write_text(json.dumps({"hospital_name": "X", "standard_charge_information": []}))
    out = tmp_path / "empty.parquet"
    result = to_parquet(src, out)
    assert not result.ok
    assert pq.read_table(out).num_rows == 0
    assert "no-charges" in {i.code for i in result.issues}


def test_record_batch_reader_with_duckdb(fixtures: Path) -> None:
    duckdb = pytest.importorskip("duckdb")
    reader = record_batch_reader(fixtures / "v3_tall.csv", batch_size=2)
    con = duckdb.connect()
    con.register("charges", reader)
    (n,) = con.execute(
        "SELECT count(*) FROM charges WHERE code = '70553' AND payer_name IS NOT NULL"
    ).fetchone()
    assert n == 4


def test_read_polars(fixtures: Path) -> None:
    pytest.importorskip("polars")
    from pricelight_parser import read_polars

    df = read_polars(fixtures / "v3_wide.csv")
    assert df.height == 4
    assert df.filter(df["code"] == "45378")["negotiated_dollar"].to_list() == [1320.0, 1710.0]


def test_rows_consumed_once(fixtures: Path) -> None:
    mrf = open_mrf(fixtures / "v3.json")
    list(mrf.rows())
    with pytest.raises(RuntimeError):
        list(mrf.rows())


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "empty"),
        (b"[1, 2, 3]", "array"),
        (b"a,b\n1,2\n", "fewer than 3"),
        (b"a,b\n1,2\nfoo,bar\n", "description"),
    ],
)
def test_unsupported_files(tmp_path: Path, content: bytes, message: str) -> None:
    path = tmp_path / "bad"
    path.write_bytes(content)
    with pytest.raises(UnsupportedFileError, match=message):
        open_mrf(path)


def test_invalid_json_reports_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text(
        '{"hospital_name": "X", "standard_charge_information": [{"description": "a",'
        ' "code_information": [], "standard_charges": [{"setting": "inpatient", "gross_charge": 5}]},'
        ' {"description": '
    )
    mrf = open_mrf(path)
    rows = list(mrf.rows())
    assert len(rows) == 1
    assert "invalid-json" in issue_codes(mrf)


def test_large_generated_json_streams(tmp_path: Path) -> None:
    """A few thousand items stream through with flat memory use."""
    items = [
        {
            "description": f"Service {i}",
            "code_information": [{"code": str(10000 + i), "type": "CPT"}],
            "standard_charges": [
                {
                    "setting": "outpatient",
                    "gross_charge": 100 + i,
                    "discounted_cash": 50 + i,
                    "minimum": 40,
                    "maximum": 90,
                    "payers_information": [
                        {
                            "payer_name": f"Payer {p}",
                            "plan_name": "Plan",
                            "standard_charge_dollar": 40 + p,
                            "methodology": "fee schedule",
                        }
                        for p in range(5)
                    ],
                }
            ],
        }
        for i in range(3000)
    ]
    path = tmp_path / "big.json.gz"
    payload = {"hospital_name": "Big", "version": "3.0.0", "standard_charge_information": items}
    path.write_bytes(gzip.compress(json.dumps(payload).encode()))
    out = tmp_path / "big.parquet"
    result = to_parquet(path, out, batch_size=1000, row_group_size=4000)
    assert result.stats.rows == 15000
    assert result.stats.payers == 5
    assert pq.ParquetFile(out).metadata.num_row_groups == 4
