# Configuration

Queuewright reads explicit local JSON bundles. It has no runtime configuration
precedence, environment-based tenant settings, credential discovery, or
network lookup.

A profile points to a desired-state manifest in the same bundle and adds
presentation and synthetic test data. Both documents use schema version `1.0`
or `1.1`; version `1.1` adds a rooted nested service tree.

## Bundled examples

| Path | Purpose |
| --- | --- |
| `queuewright/examples/minimal/profile.json` | Smallest profile |
| `queuewright/examples/minimal/desired-state.json` | Smallest desired state |
| `queuewright/examples/minimal/project-v2.json` | Smallest canonical Studio project |
| `queuewright/examples/university/profile.json` | Fictional university starter |
| `queuewright/examples/university/university.desired-state.json` | University desired state |
| `queuewright/examples/university/project-v2.json` | University canonical Studio project |
| `queuewright/contracts/schemas/` | Packaged profile, desired-state, and project schemas |

## Validate and compile

Run from the repository root after installing Queuewright:

```bash
queuewright validate queuewright/examples/minimal/profile.json
queuewright validate queuewright/examples/university/profile.json
queuewright plan queuewright/examples/minimal/profile.json
```

Use `--output /path/to/new-plan.json` to create a plan file. Queuewright
refuses non-JSON destinations, sensitive paths, profile or manifest paths, and
existing output files.

## Validation authority

JSON schemas describe portable document shape. Python validation is
authoritative for cross-document and semantic rules, including:

- matching document versions and portable identifiers;
- a reachable service tree without cycles;
- exact resource ownership and valid references;
- feature dependencies and registry-derived metadata;
- finite JSON values with no URLs or credential-shaped property names;
- dummy-mode `example.invalid` identities;
- disabled existing-object writes, deletion, notifications, and external
  effects.

Loading lives in `queuewright/configuration/loading.py`, semantic rules in
`rules.py`, `resources.py`, `automation.py`, `object_manager.py`, and `uat.py`,
and orchestration in `validation.py`. Plans are compiled by
`queuewright/planning/compiler.py`. The public entry points are
`queuewright.load_profile`, `validate_profile`, and `compile_plan`.

Validation stops at an invalid contract. A symbolic plan describes ordered
operations but does not execute them.

## Create a bundle

Copy `queuewright/examples/university/`, replace its portable identifiers,
labels, service tree, access model, policies, and synthetic test data, then
validate the copied profile. Keep `offline_only=true`, dummy identities, and
all external effects disabled.

Free-form labels require manual review for personal or organization-specific
information before publication. Contributors who change packaged examples or
contracts must also run `bash scripts/verify`.

The build-only `VITE_STATIC_DEMO=true` switch belongs to the Studio frontend;
it is not an active runtime configuration source.
