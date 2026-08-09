# Release status

Last verified: 2026-08-09 15:42 CEST

## Candidate

- Version: `0.1.0-alpha.1`
- Format: source-only prerelease
- Publication state: unpublished
- Branch: `agent/codacy-local-remediation`
- HEAD: `84cb4aa6b065882f2c5c41eaee44481191b9e032`
- Repository state: dirty local candidate with tracked refactors, tracked document
  removals, and untracked seam modules and tests
- Evidence-excluded content digest:
  `b3ef9cd9a4949f0b8177adb1280dd264d6fa1badc53b0a55e130ba87e47a6b1a`

The digest covers 184 existing Git-visible source, test, configuration, and
documentation files. It excludes generated `.repowise/`, `.codegraph/`,
`studio-ui/node_modules/`, and `studio-ui/dist/` content; local or environment
state; and the self-referential `AUDIT_LEDGER.md` and `RELEASE_STATUS.md`
evidence files.

## Current local evidence

| Check | Result |
| --- | --- |
| `python3 -m queuewright self-test` | Passed |
| `python3 -m unittest discover -s tests -p 'test_*.py' -v` | Passed, 61 tests |
| `bash scripts/verify_git_ignores.sh` | Passed |
| `npm run test` | Passed, 8 files and 25 tests |
| `npm run build` | Passed, including TypeScript checking |
| `npm run build:demo` | Passed; Pages-base artifact generated |
| `npm run test:e2e` | Passed, 1 Playwright workflow |
| Static-demo Playwright smoke at `/queuewright/` | Passed at 1440x900 and 390x844; no console errors, overlays, API requests, or remote requests |
| Codacy-bundled Ruff 0.12.7 | Passed, 0 findings across 49 Python files |
| Codacy local scan | Completed, 501 findings across Ruff, Bandit, and Pylint; no analyzer errors |
| Focused Codacy recheck for `scripts/verify_repo.py` | Passed with 0 high findings after the explicit subprocess policy fix |
| `git diff --check` and cached diff check | Passed |

`python3 scripts/verify_repo.py` passed after the remediation ledger update:
264 public-alpha files, 25 JSON documents, links, assets, public scope, Studio
contracts, and tracked Git metadata verified.

An earlier Vitest run completed 24 of 25 tests before the full App integration
case exceeded its 5-second limit while unrelated Trivy, Swift, Vitest,
PowerShell, and test workloads were active. The unchanged suite passed in full
after that host contention subsided. No timeout or quality gate was changed.

## Incomplete or external evidence

- The in-app browser runtime was unavailable. The repository Playwright suite
  and a local static-artifact Playwright smoke were used instead.
- Manual keyboard, screen-reader, zoom, reduced-motion, and cross-browser
  review remain unrun. The desktop and mobile screenshots prove visible local
  rendering only.
- Ruff is not on the interactive `PATH`; Codacy's bundled Ruff 0.12.7 supplied
  the current full-repository result without installing dependencies.
- No remote CI, Codacy Cloud, GitHub Pages deployment, signing, publication, or
  external service was invoked.

The completion audit found that `studio-ui/index.html` loaded Google Fonts.
Those links were removed, the repository verifier now rejects remote Studio
HTML assets, and the final desktop/mobile smoke observed only loopback asset
requests.

## Analyzer disposition

The local Codacy run used an external configuration and retained JSON outside
the repository. Ruff reported no findings. Bandit and Pylint reported 501
default-profile findings: 7 high, 78 warning, and 416 informational.

- Resolved: `PyLintPython3_W1510` in `scripts/verify_repo.py` by making the
  intentional `check=False` subprocess policy explicit.
- Invalid for the current contract: four test-only `Bandit_B101` assertions;
  fail-closed `PyLintPython3_W0718` around ambiguous rollback; the reported
  test-import `PyLintPython3_R0401` cycle; controlled-argument `Bandit_B603`
  calls; three intentional finite-number checks reported as
  `PyLintPython3_R0124`; and temporary resources registered with
  `unittest.addCleanup`.
- Deferred as unsupported speculative cleanup: comprehension, signature,
  duplication, line-length, and docstring advice without a demonstrated
  correctness, safety, or current maintainability defect. No ignores,
  suppressions, pattern changes, or gate changes were added.

## Remaining release gates

- review the complete eventual commit manifest and publishable examples;
- review keyboard behavior, accessibility basics, zoom, clipping, and error
  states in an interactive browser;
- recapture maintained screenshots from the final committed candidate if the
  UI changes again;
- review resolved dependency licenses and security advisories;
- configure a private vulnerability reporting route;
- run every required check from the exact commit to be tagged.

## Accepted alpha limitations

- source-checkout execution only;
- no Python package, container image, hosted Studio, or deployment manifest;
- no live Zammad discovery or apply adapter;
- no in-app IndexedDB deletion control;
- file formats and UI workflows may change before `1.0.0`;
- connected-control primitives are not available through the CLI or Studio.
