## Summary

Describe the user-visible or contract-level change.

## Safety boundary

- [ ] No secrets, tenant data, local exports, or machine-specific state.
- [ ] Active packages remain offline and independent from connected control.
- [ ] Documentation distinguishes local design state from tenant operation.

## Verification

- [ ] `bash scripts/verify`
- [ ] Connected-control tests when `experimental/connected_control/` changed.
- [ ] Manual UI checks when visible behavior changed.

List skipped checks and why:
