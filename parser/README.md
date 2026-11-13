# pricelight-parser

Streaming parser for **US hospital price transparency machine-readable files**
(45 CFR Part 180), in every layout the
[CMS templates](https://github.com/CMSgov/hospital-price-transparency) allow:
**JSON**, **CSV "tall"** and **CSV "wide"**, template versions **2.x and 3.0**.
It turns multi-gigabyte files into one tidy, normalized table, in constant
memory, and tells you what was wrong with the file.

Part of [Pricelight](https://github.com/lobojoel2003/Pricelight). This package
is licensed under the **Apache License 2.0**.

## Install

```bash
pip install pricelight-parser
```

Optional: `pip install "pricelight-parser[polars]"` for `read_polars()`.

## Use

```python
from pricelight_parser import open_mrf

mrf = open_mrf("12-3456789_example-hospital_standardcharges.json.gz")
print(mrf.format)  # MRFFormat.JSON / CSV_TALL / CSV_WIDE
print(mrf.header.hospital_name)  # available before reading any rows

for row in mrf.rows():  # one ChargeRow per item x payer/plan
    if row.code_type == "CPT" and row.code == "70553":
        print(row.payer_name, row.plan_name, row.negotiated_dollar, row.discounted_cash)

for issue in mrf.issues:  # aggregated data-quality findings
    print(issue.severity, issue.code, issue.count, issue.message)
```

Write Parquet in a single streaming pass (the parse summary is embedded in
the file's metadata):

```python
from pricelight_parser import to_parquet, read_result_metadata

result = to_parquet("hospital.csv", "hospital.parquet", constants={"hospital_id": "example"})
print(result.stats.rows, result.ok)
print(read_result_metadata("hospital.parquet")["header"]["hospital_name"])
```

Query without writing anything, with DuckDB or Polars:

```python
import duckdb
from pricelight_parser import record_batch_reader, read_polars

reader = record_batch_reader("hospital.json")
duckdb.sql("SELECT payer_name, median(negotiated_dollar) FROM reader GROUP BY ALL")

df = read_polars("hospital.csv")  # requires the polars extra
```

Discovery helpers:

```python
from pricelight_parser import parse_hpt_txt, hpt_txt_url, parse_mrf_filename

hpt_txt_url("examplehospital.org")  # 'https://examplehospital.org/cms-hpt.txt'
parse_hpt_txt(text)  # [HptEntry(location_name=..., mrf_url=...), ...]
parse_mrf_filename("123456789_example_standardcharges.csv").ein  # '12-3456789'
```

## Command line

```bash
pricelight-parse inspect hospital.json.gz       # summary + sample rows + issues
pricelight-parse convert hospital.csv -o out.parquet --hospital-id example
pricelight-parse validate hospital.csv          # exit code 1 if errors
pricelight-parse hpt-txt cms-hpt.txt            # parse a discovery file to JSON
```

## What it handles

- Layouts: JSON, CSV tall, CSV wide (payer/plan columns unpivoted).
- Versions: v2.x (`affirmation`, `hospital_location`, `estimated_amount`,
  `modifiers`) and v3.0 (`attestation`, `attester_name`, `type_2_npi`,
  `median_amount`, `10th_percentile`, `90th_percentile`, `count`,
  `modifier_code`).
- Containers: plain, gzip, zip, bzip2, xz (zstd with the `zstandard`
  package), detected from magic bytes.
- Text: UTF-8 with or without BOM, Windows-1252, CRLF, ragged rows, padded
  or mixed-case headers.
- Repairs (each one logged): `$1,020.00` / `N/A` in numeric fields, code-type
  variants (`MSDRG`, `rev code`), abbreviated settings (`OP`), methodology
  variants (`fee_schedule`), `M/D/YYYY` dates, DRG/revenue-code padding.
- JSON metadata placed after the charge array (read with a second pass only
  when needed; `full_metadata=True` forces it).

## Performance

Measured with `scripts/benchmark.py` on one core (Python 3.13): a 1 GB JSON
file (7.3M rows) in 75 s and a 1 GB CSV (8.4M rows) in 105 s, peak memory
under 300 MB. Memory does not grow with file size.

## Not a validator

`validate` checks the CMS header and conditional requirements that matter
for using the data. It is not the official CMS validator
(<https://cmsgov.github.io/hpt-tool/>).

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.
