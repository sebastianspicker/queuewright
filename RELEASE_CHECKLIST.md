# `0.1.0-alpha.1` release checklist

## Candidate files

- [ ] Review the complete commit manifest.
- [ ] Confirm that secrets, private data, local state, caches, logs, exports,
  and browser artifacts are absent.
- [ ] Review every publishable configuration example.
- [ ] Confirm that `requirements-control.txt` matches the connected-control
  dependency used by tests.
- [ ] Confirm that `studio-ui/package-lock.json` matches `package.json`.
- [ ] Review resolved dependency licenses and security findings.
- [ ] Confirm that private vulnerability reporting is available.

## Automated checks

- [ ] `python3 -m queuewright self-test`
- [ ] `python3 -m unittest discover -s tests -v`
- [ ] `python3 scripts/verify_repo.py`
- [ ] `npm ci` from `studio-ui/`
- [ ] `npm run test` from `studio-ui/`
- [ ] `npm run build` from `studio-ui/`
- [ ] `npm run test:e2e` from `studio-ui/`
- [ ] `git diff --check`

## Manual checks

- [ ] Review desktop and mobile layouts.
- [ ] Test keyboard navigation and focus visibility.
- [ ] Check loading, empty, error, disabled, and unavailable-service states.
- [ ] Check zoom, clipping, and reduced-motion behavior.
- [ ] Confirm that screenshots contain fictional data only.
- [ ] Confirm that documentation links, commands, paths, and examples match the
  candidate.

## Publication

- [ ] Re-run all checks from the candidate commit.
- [ ] Confirm the full commit identifiers used for GitHub Actions.
- [ ] Create tag `v0.1.0-alpha.1`.
- [ ] Publish
  [`docs/releases/0.1.0-alpha.1.md`](docs/releases/0.1.0-alpha.1.md)
  as a GitHub prerelease.
