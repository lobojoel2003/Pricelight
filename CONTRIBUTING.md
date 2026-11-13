# Contributing to Pricelight

Thanks for helping make hospital prices readable. Bug reports, file samples
that break the parser, design feedback and code are all welcome.

## Getting set up

You need [uv](https://docs.astral.sh/uv/) and Node.js 20.19 or newer.

```bash
make setup      # uv sync + npm ci
make demo       # build the synthetic dataset into site/public/data
make dev        # http://localhost:5173
```

## Before you open a pull request

```bash
make check      # versions, ruff, mypy --strict, prettier, svelte-check, all unit tests
make e2e        # Playwright end-to-end tests (desktop + phone)
```

- Add or update tests with your change. Parser fixes should come with a small
  fixture in `parser/tests/fixtures/` that reproduces the problem. Never
  commit real patient data; hospital price files contain none, but keep it
  that way.
- Add a line under **Unreleased** in `CHANGELOG.md` for user-visible changes.
- Keep the site free of third-party requests (fonts, analytics, CDNs, map
  tiles). The end-to-end tests enforce this.

## Licensing of contributions

The repository has two licenses (see the README):

- `parser/` is **Apache-2.0**. Contributions there must be your own work or
  Apache-compatible; do not copy code from the AGPL parts into `parser/`.
- Everything else is **AGPL-3.0-or-later**.

By submitting a contribution you agree that it is licensed under the license
of the directory it lands in.

## Reporting a broken hospital file

Use the "A hospital file doesn't parse correctly" issue template and include
a link to the public file and the output of:

```bash
uv run pricelight-parse validate path/to/file
```

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
