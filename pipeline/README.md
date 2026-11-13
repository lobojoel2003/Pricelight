# pricelight (pipeline)

The data pipeline behind [Pricelight](https://github.com/lobojoel2003/Pricelight):
discover hospital price files, download them, parse them with
[`pricelight-parser`](https://github.com/lobojoel2003/Pricelight/tree/main/parser)
into a Parquet lake, and build the compact dataset the Pricelight web app
searches, using DuckDB and Polars.

Licensed under the **GNU AGPL v3.0 or later**.

## Commands

```bash
pricelight demo                       # synthetic demo dataset (fictional hospitals)
pricelight discover example.org       # read cms-hpt.txt into data/manifest.csv
pricelight fetch                      # streaming downloads with ETag/Last-Modified caching
pricelight geocode                    # fill coordinates via the US Census geocoder
pricelight ingest --jobs 8            # parse into data/lake (incremental, parallel)
pricelight build --publish site/public/data
pricelight run [--demo]               # ingest + build in one go
pricelight report                     # file-quality summary across hospitals
pricelight query "mri brain" --state TX --payer "Northwind Health"
```

All commands accept `--data DIR` (default `./data`, or `$PRICELIGHT_DATA`).
See the [main README](https://github.com/lobojoel2003/Pricelight#readme) and
[docs/](https://github.com/lobojoel2003/Pricelight/tree/main/docs) for the data
layout and the site dataset format.
