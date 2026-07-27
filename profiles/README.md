# Profiles

`profiles/example/` contains the smallest bundled offline configuration:

- `profile.json` defines the profile metadata, presentation, fictional
  identities, and internal test expectations;
- `desired-state.json` defines the symbolic managed resources.

Validate it from the repository root:

```bash
python3 -m queuewright validate profiles/example/profile.json
```

Compile its plan:

```bash
python3 -m queuewright plan profiles/example/profile.json
```

Use the larger
[`studio/templates/university/`](../studio/templates/university/README.md)
bundle as a starting point for Studio. The profile contract is documented in
[`docs/REUSABLE_CONFIGURATION.md`](../docs/REUSABLE_CONFIGURATION.md).

Profiles must not contain tenant URLs, credentials, personal data, or live
snapshots.
