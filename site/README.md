# Pricelight site

Svelte 5 + Vite + TypeScript web app. AGPL-3.0-or-later.

```bash
npm ci
npm run dev        # needs a dataset in public/data: run `make demo` at the repo root
npm run check      # svelte-check (strict TypeScript)
npm test           # vitest unit tests
npm run build      # production build in dist/
npm run e2e        # Playwright tests against `npm run preview`
```

`src/lib/` holds the logic (search, aggregation, scales, URL state, the
Parquet engine and the lazy DuckDB SQL engine); `src/components/` the UI.
`scripts/screenshots.mjs` regenerates the README images.
