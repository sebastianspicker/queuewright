# Release status

## Candidate

- Version: `0.1.0-alpha.1`
- Format: source-only prerelease
- Publication state: unpublished
- Repository state: no commits; all candidate files are untracked

## Verified locally

The following checks have current local evidence:

| Check | Result |
|---|---|
| `python3 -m queuewright self-test` | Passed |
| Example and university validation | Passed |
| Example plan to standard output | Passed |
| Example plan written with `--output` | Passed and byte-identical to standard output |
| `python3 -m unittest discover -s tests -v` | Passed, 58 tests |
| `python3 scripts/verify_repo.py` | Passed |
| `npm ci` | Passed, 134 packages audited with no reported vulnerabilities |
| `npm run test` | Passed, 3 files and 13 tests |
| `npm run build` | Passed, including TypeScript checking |
| Screenshot file and visible-content review | Completed for both tracked files |

`npm run test:e2e` is blocked because an unrelated local process already owns
port `8765`. Playwright correctly refused to reuse it.

## Open release gates

- review the first commit manifest;
- review all publishable configuration examples;
- pass the browser test with ports `5173` and `8765` available;
- review keyboard behavior, accessibility basics, zoom, clipping, and error
  states in a browser;
- recapture screenshots from the final candidate;
- review dependency licenses and security findings;
- configure a private vulnerability reporting route;
- run all checks from the exact commit to be tagged.

## Accepted alpha limitations

- source-checkout execution only;
- no Python package, container image, hosted Studio, or deployment manifest;
- no live Zammad discovery or apply adapter;
- no in-app IndexedDB deletion control;
- file formats and UI workflows may change before `1.0.0`;
- connected-control primitives are not available through the CLI or Studio.
