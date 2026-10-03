# Examples

`minimal/` contains the smallest bundled offline configuration:

- `profile.json` defines the profile metadata, presentation, fictional
  identities, and internal test expectations;
- `desired-state.json` defines the symbolic managed resources;
- `project-v2.json` is the same bundle as a canonical Blueprint V2 Studio
  project.

Validate it from the repository root:

```bash
python3 -m queuewright validate queuewright/examples/minimal/profile.json
```

Compile its plan:

```bash
python3 -m queuewright plan queuewright/examples/minimal/profile.json
```

Use the larger
[`university/`](university/README.md)
bundle as a starting point for Studio. The profile contract is documented in
[`docs/CONFIGURATION.md`](../../docs/CONFIGURATION.md).

Profiles must not contain tenant URLs, credentials, personal data, or live
snapshots.
