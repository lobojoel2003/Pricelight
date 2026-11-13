# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest

from pricelight_parser import parse_hpt_txt, parse_mrf_filename, parse_wide_header
from pricelight_parser.cli import main
from pricelight_parser.hpt_txt import hpt_txt_url
from pricelight_parser.models import Code
from pricelight_parser.normalize import (
    IssueLog,
    make_codes,
    normalize_code,
    normalize_methodology,
    normalize_setting,
    parse_bool,
    parse_date,
    parse_number,
    primary_code,
    split_modifiers,
    split_multi,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (12, 12.0),
        (12.5, 12.5),
        ("1,234.50", 1234.5),
        ("$99", 99.0),
        (" 7 ", 7.0),
        ("62.5%", 62.5),
        ("N/A", None),
        ("", None),
        (None, None),
        (True, None),
        ("abc", None),
        ("nan", None),
    ],
)
def test_parse_number(raw: object, expected: float | None) -> None:
    assert parse_number(raw) == expected


def test_parse_number_logs() -> None:
    log = IssueLog()
    parse_number("$5", log)
    parse_number("x", log)
    parse_number(-3, log)
    assert {i.code for i in log.issues} == {
        "formatted-number",
        "non-numeric-value",
        "non-positive-number",
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-07-01", "2024-07-01"),
        ("7/1/2024", "2024-07-01"),
        ("07/01/2024", "2024-07-01"),
        ("2024-07-01T00:00:00Z", "2024-07-01"),
        (None, None),
        ("someday", "someday"),
    ],
)
def test_parse_date(raw: object, expected: str | None) -> None:
    assert parse_date(raw) == expected


def test_parse_bool() -> None:
    assert parse_bool("TRUE") is True
    assert parse_bool("false") is False
    assert parse_bool(True) is True
    assert parse_bool("maybe") is None
    assert parse_bool("") is None


def test_codes_and_priority() -> None:
    log = IssueLog()
    codes = make_codes(
        [
            ("4410001", "CDM"),
            ("70553", "cpt"),
            ("70553", "CPT"),
            ("0120", "rev code"),
            (None, "CPT"),
        ],
        log,
    )
    assert codes == [Code("4410001", "CDM"), Code("70553", "CPT"), Code("0120", "RC")]
    assert primary_code(codes) == Code("70553", "CPT")
    assert primary_code([]) is None
    drg = make_codes([("DRG 0470", "MS DRG")])
    assert drg == [Code("470", "MS-DRG")]
    assert primary_code([Code("70553", "CPT"), Code("470", "MS-DRG")]).type == "MS-DRG"
    assert normalize_code("120", "RC") == "0120"
    assert normalize_code("g 0105", "HCPCS") == "G0105"
    log2 = IssueLog()
    make_codes([("1", "XYZ")], log2)
    assert "unknown-code-type" in {i.code for i in log2.issues}


def test_settings_and_methodology() -> None:
    assert normalize_setting("Inpatient") == "inpatient"
    assert normalize_setting("OP") == "outpatient"
    assert normalize_setting("both") == "both"
    log = IssueLog()
    assert normalize_setting("ER", log) == "er"
    assert normalize_setting(None, log) is None
    assert {i.code for i in log.issues} == {"invalid-setting", "missing-setting"}
    assert normalize_methodology("Fee Schedule") == "fee schedule"
    assert normalize_methodology("case_rate") == "case rate"
    assert (
        normalize_methodology("Percent of Total Billed Charge") == "percent of total billed charges"
    )
    assert normalize_methodology(None) is None


def test_split_helpers() -> None:
    assert split_multi("a | b ||c") == ["a", "b", "c"]
    assert split_multi(["a", " ", None]) == ["a"]
    assert split_multi(None) == []
    assert split_modifiers("25|59, lt") == ["25", "59", "LT"]
    assert split_modifiers(["50"]) == ["50"]


def test_issue_log_merges_and_caps_examples() -> None:
    log = IssueLog(max_examples=2)
    for i in range(5):
        log.warn("x", "msg", where=f"row {i}")
    log.error("y", "bad")
    issues = log.issues
    assert [i.code for i in issues] == ["y", "x"]
    assert issues[1].count == 5
    assert issues[1].examples == ["row 0", "row 1"]
    assert log.has_errors
    assert len(log) == 2


def test_wide_header() -> None:
    assert parse_wide_header("standard_charge|Aetna|Choice|POS II|negotiated_dollar") == (
        "negotiated_dollar",
        "Aetna",
        "Choice|POS II",
    )
    assert parse_wide_header("standard_charge|Aetna|negotiated_dollar") == (
        "negotiated_dollar",
        "Aetna",
        None,
    )
    assert parse_wide_header("estimated_amount | Cigna | OAP") == (
        "estimated_amount",
        "Cigna",
        "OAP",
    )
    assert parse_wide_header("standard_charge|gross") is None
    assert parse_wide_header("description") is None


def test_hpt_txt(fixtures: Path) -> None:
    entries = parse_hpt_txt((fixtures / "cms-hpt.txt").read_text())
    assert len(entries) == 2
    assert entries[1].location_name == "Example Valley Clinic"
    assert entries[1].mrf_url.endswith(".csv")
    # repeated keys without a blank line still split entries
    entries = parse_hpt_txt("mrf-url: a\nlocation-name: A\nmrf-url: b\nlocation-name: B\n")
    assert [e.mrf_url for e in entries] == ["a", "b"]
    assert parse_hpt_txt("garbage") == []
    assert hpt_txt_url("https://www.example.org/x/y?z=1") == "https://www.example.org/cms-hpt.txt"


def test_mrf_filename() -> None:
    parsed = parse_mrf_filename("https://x.org/a/123456789_my-hospital_standardcharges.csv")
    assert parsed is not None
    assert parsed.ein == "12-3456789"
    assert parsed.hospital_slug == "my-hospital"
    assert parsed.extension == "csv"
    assert parse_mrf_filename("prices.json") is None


def test_cli(fixtures: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inspect", str(fixtures / "v3.json")]) == 0
    out = capsys.readouterr().out
    assert "Example Lake Hospital" in out and "json" in out

    assert main(["inspect", "--json", "--rows", "1", str(fixtures / "v3_wide.csv")]) == 0
    assert '"csv-wide"' in capsys.readouterr().out

    target = tmp_path / "x.parquet"
    meta = tmp_path / "x.json"
    code = main(
        ["convert", str(fixtures / "v3_tall.csv"), "-o", str(target), "--meta", str(meta), "-q"]
    )
    assert code == 0 and target.exists() and meta.exists()

    assert main(["validate", str(fixtures / "v3_wide.csv")]) == 0
    assert main(["validate", "--json", str(fixtures / "messy_v2_tall.csv")]) == 1
    capsys.readouterr()

    assert main(["hpt-txt", str(fixtures / "cms-hpt.txt")]) == 0
    assert "Example Valley Clinic" in capsys.readouterr().out

    assert main(["inspect", str(tmp_path / "missing.json")]) == 2
