# Architecture

Pricelight has three parts with a strict dependency direction:

```
pricelight-parser  (Apache-2.0)   knows the CMS file formats, nothing else
        ▲
pricelight         (AGPL-3.0)     manifest, downloads, Parquet lake, DuckDB build
        ▲  writes a static dataset
site               (AGPL-3.0)     reads that dataset in the browser
```

The parser never imports the pipeline, and the site never talks to Python:
the only interface between pipeline and site is five static files.

## 1. Parser (`parser/`)

`open_mrf(path)` returns a streaming parser for one machine-readable file
(MRF).

- **Source handling** (`sources.py`): compression is sniffed from magic bytes
  (gzip, zip, bzip2, xz, optional zstd). For zip archives the largest
  `.json`/`.csv` member is used. Text encoding is UTF-8 (with/without BOM) or
  Windows-1252. A `Source` can be reopened, because JSON may need two passes.
- **Format detection**: `{` → JSON; otherwise CSV, and row 3 decides tall
  (has `payer_name`) vs wide (`standard_charge|<payer>|<plan>|…` headers).
- **JSON** (`json_format.py`): a short event-level pre-scan collects metadata
  that precedes `standard_charge_information`, then `ijson.items` (C backend)
  streams the array one item at a time. If required metadata is missing
  (keys after the array), a second pass reads the tail. Memory is bounded by
  the largest single item.
- **CSV** (`csv_format.py`): rows 1–2 hold general data elements, row 3 the
  column headers. Wide files are unpivoted into one row per payer/plan. In
  tall files, item columns repeated across payer rows are parsed once.
- **Normalization** (`normalize.py`): numbers, dates, code types, settings,
  methodologies, modifiers. Every repair or defect is counted in an
  `IssueLog` (merged per issue code, with a few example locations).
- **Output** (`writer.py`): rows are batched into Arrow record batches and
  written as Parquet (zstd) row groups; the parse summary is embedded in the
  Parquet key-value metadata under `pricelight`.

## 2. Pipeline (`pipeline/`)

```
data/
  manifest.csv                                 hospitals: id, name, address, lat/lon, URLs
  raw/<id>/<file>, raw/<id>/_fetch.json        downloads + ETag/Last-Modified state
  lake/charges/hospital_id=<id>/charges.parquet
  lake/charges/hospital_id=<id>/_ingest.json   fingerprint for incremental re-runs
  lake/hospitals.parquet                       one row per hospital: file facts, quality
  site/                                        the dataset the web app reads
```

- `ingest` runs `to_parquet` per hospital in a process pool (spawned, not
  forked, because DuckDB/Arrow threads may be running). A hospital is skipped
  when its file size/mtime and the parser version match the last successful
  ingest. Partitions of hospitals removed from the manifest are deleted.
- `build` (DuckDB) reads the lake with Hive partitioning and:
  1. keeps comparable billing code systems (CPT, HCPCS, DRG families, …);
  2. picks one setting per service × hospital (DRGs: inpatient; procedure
     codes: outpatient, then "both");
  3. prefers lines without modifiers when a hospital lists both;
  4. normalizes payer names (Python, on the small set of distinct names);
  5. aggregates to one item row per service × hospital (median gross and
     cash, reported min/max) and one row per service × hospital × payer ×
     plan (median dollar rate, else median/estimated allowed amount);
  6. writes `prices.parquet` **sorted by service** with 8,192-row groups, so
     each row group's min/max statistics cover a narrow band of services.

  Polars shapes the JSON indexes and the quality report.

## 3. Site (`site/`)

Svelte 5 (runes) + Vite + TypeScript, no UI framework.

- On load it fetches `meta.json`, `hospitals.json`, `services.json` and
  `payers.json` (small) and draws the map immediately.
- A search reads the Parquet footer once (cached), then fetches **only the row
  groups whose `service` statistics can contain the requested code**, via
  HTTP range requests ([hyparquet](https://github.com/hyparam/hyparquet)).
  Results are cached per service.
- The SQL explorer lazy-loads DuckDB-WASM, reads the rows with hyparquet and
  inserts them as an Arrow table, so DuckDB never downloads its Parquet
  extension from a third-party CDN. Extension autoloading is disabled.
- The map uses `us-atlas` boundaries pre-projected to Albers USA (Alaska and
  Hawaii insets) and d3-zoom; there is no tile server.
- State lives in one `AppState` class (`src/lib/state.svelte.ts`) and is
  mirrored to the URL, so every view is a shareable link and the back button
  works.

### Why not a server?

Health searches are sensitive. With a static dataset and client-side reads,
the host only sees requests for byte ranges of one file, never a query
string with a procedure name. It also means the whole site can be hosted
for free on GitHub Pages or any static host, and keeps working offline once
loaded.
