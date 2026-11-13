# Changelog

All notable changes to Pricelight are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). All components
(parser, pipeline and site) share one version number.

## [Unreleased]

## [0.1.0] - 2026-11-13

First public release.

### Parser (`pricelight-parser`, Apache-2.0)

- Streaming parser for all three CMS hospital price transparency layouts:
  JSON, CSV "tall" and CSV "wide", template versions 2.x and 3.0 (including
  v3 median / 10th / 90th percentile allowed amounts and counts).
- Constant-memory streaming of multi-gigabyte files: ijson's C backend for
  JSON, row-at-a-time CSV, batched Arrow record batches, Parquet output.
- Reads plain, gzip, zip, bzip2 and xz files, detected from magic bytes;
  detects UTF-8 (with or without BOM) and Windows-1252 text.
- Normalizes code types (`MSDRG` → `MS-DRG`), DRG and revenue code padding,
  settings (`OP` → `outpatient`), methodologies and messy numbers
  (`$1,020.00`, `N/A`), and logs each fix as a data-quality issue.
- Lightweight validation of CMS conditional requirements and header fields,
  aggregated into an issue report.
- `cms-hpt.txt` discovery file parser and CMS MRF file-name parser.
- Arrow `RecordBatchReader` and Polars helpers for direct use with DuckDB
  and Polars.
- `pricelight-parse` CLI: `inspect`, `convert`, `validate`, `hpt-txt`.

### Pipeline (`pricelight`, AGPL-3.0)

- `pricelight` CLI: `discover` (cms-hpt.txt), `fetch` (streaming downloads
  with ETag / Last-Modified caching and retries), `geocode` (US Census
  geocoder), `ingest` (parallel, incremental Parquet lake), `build` (DuckDB
  + Polars site dataset), `report`, `query` and `run`.
- Payer-name normalization so one insurer can be compared across hospitals.
- Plain-language labels for 48 commonly shopped services (CMS shoppable
  services list plus everyday services).
- Synthetic demo dataset generator: 60 fictional hospitals in every CMS
  layout, version and compression, with realistic data-quality defects.

### Site (AGPL-3.0)

- Svelte 5 web app with a US map (Albers USA, Alaska and Hawaii insets) and a
  price-range bar per hospital showing the cash price next to every
  insurer's negotiated rate on a shared axis.
- Search by plain words, synonyms or billing code; filter by insurer and
  state; sort by cash price, insurer rate or typical rate; shareable URLs.
- Hospital pages with the full insurer table, file freshness and
  data-quality findings.
- Prices are read straight from a static Parquet file with HTTP range
  requests in the browser: no server, no cookies, no third-party requests.
- SQL explorer powered by DuckDB-WASM, loaded only on demand.
- Light and dark themes with colorblind-safe, validated chart colors;
  keyboard and screen-reader support; responsive phone layout.

### Project

- GitHub Actions CI (Python 3.10–3.13 on Linux, macOS and Windows; site
  type-check, unit and end-to-end tests), CodeQL, Dependabot, GitHub Pages
  deployment and tag-driven releases with build provenance attestations.
- Single-source versioning (`VERSION`) with build numbers and commit hashes
  embedded in the site and dataset.

[Unreleased]: https://github.com/lobojoel2003/Pricelight/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/lobojoel2003/Pricelight/releases/tag/v0.1.0
