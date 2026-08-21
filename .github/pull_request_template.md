## Summary

Describe the user-visible or contract-level change.

## Safety boundary

- [ ] No secrets, tenant data, machine-specific tool state, exports, or local work logs are included.
- [ ] Offline packages remain free of network, credential, environment, and apply behavior.
- [ ] Documentation distinguishes design-ready from tenant-applied state.

## Verification

- [ ] `python3 -m queuewright self-test`
- [ ] `python3 -m unittest discover -s tests -v`
- [ ] `python3 scripts/verify_repo.py`
- [ ] `bash scripts/verify_git_ignores.sh`
- [ ] `npm run test` (`studio-ui/`, when affected)
- [ ] `npm run build` (`studio-ui/`, when affected)

List skipped checks and why:
