# Release status

Last verified: 2026-08-18

Queuewright is an unpublished, source-only alpha. No commit is currently
designated as a release candidate. The checks below were run from commit
`4f331be1fef1032aef97dbfddb59f0aee77f4ee0` on branch
`agent/codacy-local-remediation` before this documentation update.

## Local evidence

| Check | Result |
| --- | --- |
| `python3 -m queuewright self-test` | Passed |
| `python3 -m unittest discover -s tests -p 'test_*.py' -v` | Passed, 75 tests |
| `python3 scripts/verify_repo.py` | Passed, 842 public-alpha files and 28 JSON documents |
| `npm run test` in `studio-ui/` | Passed, 10 files and 40 tests |
| `npm run build` in `studio-ui/` | Passed |
| `npm run build:demo` in `studio-ui/` | Passed with the `/queuewright/` Pages base path |
| `npm run test:e2e` in `studio-ui/` | Not run successfully: the local Playwright Chromium executable is absent |

The repository verifier intentionally excludes `.env.example` contents from
automated inspection. That file still requires manual owner review before a
release.

## Release gates

- Review the exact commit and file manifest intended for publication.
- Review keyboard behavior, accessibility basics, zoom, clipping, and error
  states in an interactive browser.
- Run the Playwright workflow with its pinned browser available.
- Recapture maintained screenshots if the final UI changes.
- Review resolved dependency licenses and security advisories.
- Configure a private vulnerability-reporting route.
- Run the complete release checks from the commit intended for tagging.

## Alpha limitations

- Source-checkout execution only; there is no published Python package,
  container image, hosted Studio, or deployment manifest.
- There is no live Zammad discovery or apply adapter.
- The Studio does not provide an in-app IndexedDB deletion control.
- Connected-control primitives are not available through the CLI or Studio.
- File formats and UI workflows may change before `1.0.0`.

No remote CI, GitHub Pages deployment, package publication, signing, or
external service was exercised by this local verification.
