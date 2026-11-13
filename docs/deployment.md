# Running your own instance

## GitHub Pages (demo data)

The [`pages.yml`](../.github/workflows/pages.yml) workflow builds the demo
dataset and the site on every push to `main` and deploys it to GitHub Pages.
One-time setup: **Settings → Pages → Build and deployment → Source: GitHub
Actions**. Until Pages is enabled the workflow still builds, skips the
deploy step and explains what to do in the run summary.

## Real data

1. Create `data/manifest.csv` with `pricelight discover <website> …`, or by
   hand with these columns:

   `id,name,address,city,state,zip,lat,lon,website,source_page_url,mrf_url,mrf_path,ccn`

   `id` must be lowercase letters, digits and dashes. Set either `mrf_url`
   (downloaded by `fetch`) or `mrf_path` (a local file, relative to `data/`).
2. Download: `uv run pricelight fetch` (re-runs only download changed files).
3. Coordinates: `uv run pricelight geocode` fills missing `lat`/`lon` with the
   US Census geocoder. Hospitals without coordinates are listed but not drawn
   on the map.
4. Build: `uv run pricelight run --min-hospitals 2 --publish site/public/data`.
   `--min-hospitals` drops codes only one hospital lists, which keeps
   `services.json` small at national scale.
5. Ship `site/`: `cd site && npm ci && npm run build` and serve `site/dist`
   from any static host. Requirements for the host:
   - HTTP **range requests** for `data/prices.parquet` (GitHub Pages,
     Netlify, Cloudflare Pages, S3/CloudFront, nginx and Caddy all support
     them);
   - `application/wasm` MIME type for the SQL explorer's DuckDB file.

The build is base-path independent (`base: './'`), so it works at a domain
root or in a sub-directory without configuration.

## Scale notes

- Parsing is roughly 80–100k rows per second per core; `ingest --jobs N`
  parses N hospitals in parallel, and unchanged files are skipped.
- `prices.parquet` is sorted by service with 8,192-row groups. A browser
  search downloads the footer once and then only the row groups that can
  contain the service, so lookup cost depends on how many hospitals list the
  service, not on the size of the dataset.
- The SQL explorer loads the whole dataset into the browser; for national
  datasets, point researchers to the Parquet lake instead.
