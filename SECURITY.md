# Security policy

## Supported versions

Security fixes are made on the latest release. Pricelight is pre-1.0, so
please upgrade to the newest version before reporting.

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through
[GitHub security advisories](https://github.com/lobojoel2003/Pricelight/security/advisories/new).
Include steps to reproduce and the affected component (site, pipeline,
parser, CI). You will get an acknowledgement within a week.

## Scope notes

- The website is static and makes no third-party requests; a change that
  leaks what a visitor searches for (to the host or anyone else) is treated
  as a security issue.
- The parser reads untrusted files from the internet. Crashes are bugs;
  resource exhaustion that defeats streaming (unbounded memory on a crafted
  file), path traversal from archive member names, or code execution are
  security issues.
