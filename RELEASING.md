# Release procedure

Queuewright has no automated package-publication or GitHub Release workflow.
The Pages workflow deploys only the client-side Studio demo. Tags, release
notes, and any package publication are manual maintainer actions.

Prepare a release from one reviewed commit and complete every applicable item
below from that exact commit. Do not infer tenant operation, hosted API
behavior, browser compatibility, or accessibility conformance from local
automated checks.

## Candidate review

- [ ] Review the complete commit manifest and ignored-file boundary.
- [ ] Review examples, documentation, and screenshots for fictional data only.
- [ ] Review resolved Python and npm dependency licenses and advisories.
- [ ] Confirm GitHub private vulnerability reporting is available.
- [ ] Confirm documentation paths, commands, versions, and limitations match
  the candidate.

## Automated checks

```bash
python3 -m pip install '.[dev]'
npm --prefix studio-ui ci
bash scripts/verify
python3 -m pip install ./experimental/connected_control
python3 scripts/verify_control_package.py
git diff --check
```

## Manual Studio review

- [ ] Review desktop and mobile layouts, keyboard flow, visible focus, zoom,
  clipping, reduced motion, and loading, empty, error, and unavailable-service
  states.
- [ ] Confirm screenshots contain only current fictional data and no unrelated
  desktop content.
- [ ] Confirm the static demo performs no API request or browser persistence.

## Publication

- [ ] Re-run all checks from the exact candidate commit.
- [ ] Confirm GitHub Actions are pinned to immutable commits.
- [ ] Create the intended tag and release notes manually.
- [ ] Verify the resulting public artifacts and Pages deployment separately;
  local checks do not prove remote publication.
