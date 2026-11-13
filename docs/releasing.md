# Releasing

Pricelight follows [Semantic Versioning](https://semver.org). The parser,
pipeline and site share one version, stored in [`VERSION`](../VERSION) and
mirrored into every manifest by `scripts/version.py`.

## Build numbers

Every CI build is stamped with:

- **version**: from `VERSION` (or the tag, in release builds);
- **build number**: the GitHub Actions run number (`PRICELIGHT_BUILD_NUMBER`);
- **commit**: the short git SHA (`PRICELIGHT_COMMIT`).

They appear in the site footer and About dialog, in the dataset's
`meta.json`, and in the release's `BUILD_INFO.json`. Local builds show
build `dev`.

## Cutting a release

1. Make sure `main` is green and the **Unreleased** section of
   [`CHANGELOG.md`](../CHANGELOG.md) describes the changes.
2. Bump everything at once (also moves Unreleased into a dated section):

   ```bash
   python3 scripts/version.py bump minor
   ```

3. Refresh the lock file and verify:

   ```bash
   uv lock && make check
   ```

4. Commit and tag (annotated):

   ```bash
   git commit -am "Release v0.2.0" && git tag -a v0.2.0 -m "Pricelight v0.2.0"
   ```

5. Push the branch and the tag:

   ```bash
   git push origin main --follow-tags
   ```

The [release workflow](../.github/workflows/release.yml) then:

1. checks that the tag matches every component version and the changelog;
2. runs lint, type checks and tests;
3. builds `pricelight-parser` and `pricelight` wheels and sdists
   (`twine check --strict`);
4. builds the demo dataset and the static site;
5. writes `BUILD_INFO.json` and `SHA256SUMS.txt`;
6. attests build provenance (`gh attestation verify <file> --repo lobojoel2003/Pricelight`);
7. publishes a GitHub release with the changelog section as notes.

Tags with a pre-release suffix (`v0.2.0-rc.1`) are published as
pre-releases.

### Releasing from the GitHub UI

Instead of pushing a tag you can open **Actions → Release → Run workflow**,
pick the branch (usually `main`) and enter the tag, e.g. `v0.2.0`. If the tag
doesn't exist yet, the workflow builds and tests that branch's head commit
and creates the tag at exactly that commit when it publishes the release.
Running it for an existing tag re-builds and re-uploads that release.

## Publishing to PyPI (optional)

1. On PyPI, add a trusted publisher for both projects (`pricelight-parser`,
   `pricelight`): repository `lobojoel2003/Pricelight`, workflow
   `release.yml`, environment `pypi`.
2. In GitHub, create an environment named `pypi` and set the repository
   variable `PUBLISH_TO_PYPI` to `true`.

The next release uploads the wheels and sdists with OIDC; no API token is
stored.
