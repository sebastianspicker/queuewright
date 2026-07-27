# Reusable configuration

Queuewright profiles are local JSON bundles. A profile points to a
desired-state manifest, adds presentation and synthetic test data, and sets
safety rules for plan compilation.

The CLI does not read environment variables, discover credentials, or contact
Zammad.

## Files

| Path | Purpose |
|---|---|
| `profiles/example/profile.json` | Minimal profile |
| `profiles/example/desired-state.json` | Minimal desired state |
| `studio/templates/university/profile.json` | University starter profile |
| `studio/templates/university/university.desired-state.json` | University starter desired state |
| `schemas/queuewright-profile.schema.json` | Profile structure |
| `schemas/queuewright-desired-state.schema.json` | Desired-state structure |

The profile and manifest remain separate:

- the manifest defines symbolic managed resources and relationships;
- the profile defines identity templates, labels, positions, test scenarios,
  and expected checks.

## Validate and compile

Validate the minimal example:

```bash
python3 -m queuewright validate profiles/example/profile.json
```

Validate the university starter:

```bash
python3 -m queuewright validate \
  studio/templates/university/profile.json
```

Compile a plan:

```bash
python3 -m queuewright plan profiles/example/profile.json
```

Write a plan to a new file:

```bash
python3 -m queuewright plan profiles/example/profile.json \
  --output /tmp/example-plan.json
```

`validate` prints a canonical JSON summary. `plan` prints canonical JSON unless
`--output` is supplied. File output is exclusive and refuses to replace an
existing file or either input document.

## Profile overview

The schemas define the exact JSON document shapes. The Python validator is the
authoritative implementation of the cross-document constraints summarized here.

A profile includes:

| Field | Contract |
|---|---|
| `schema_version` | `1.0` for flat groups or `1.1` for a rooted nested service tree |
| `profile_key` | Lowercase portable identifier |
| `offline_only` | Must be `true` |
| `manifest` | Relative path to a JSON manifest |
| `identity` | Dummy-mode login and `example.invalid` email templates |
| `presentation` | Labels, options, workflow text, and positions |
| `uat` | Internal test scenarios, seed matrix, and expected checks |

The Python validator enforces cross-file rules, including:

- no URLs or sensitive local paths;
- `allow_existing_object_writes=false`;
- `allow_delete=false`;
- managed prefixes and technical namespaces;
- one reachable root for schema `1.1`;
- valid parent, role, organization, field, option, and workflow references;
- unshared organizations with domain assignment disabled;
- dummy-mode identity templates with email addresses ending in
  `@example.invalid`;
- inactive checklists;
- fenced automation with no external effects;
- internal-only retained test cases;
- complete labels and positions for configurable fields and workflows.

Validation stops on the first invalid contract. Unknown references are not
discarded or converted into external identifiers.

Names, labels, descriptions, and other free-form text require manual review to
confirm that they do not identify real people or organizations.

## Create another profile

1. Copy `studio/templates/university/` to a new directory.
2. Change `profile_key`, `manifest_key`, `managed_prefix`, and
   `technical_namespace`.
3. Replace the service tree, organizations, roles, support-account templates,
   labels, schedules, and test scenarios.
4. Keep all identity templates in dummy mode, review free-form text for real
   identities, and keep all external effects disabled.
5. Run `validate`, `plan`, the Python test suite, and
   `scripts/verify_repo.py`.
6. Review the symbolic plan as a local artifact. It is not an apply command.

Use `profiles/example/` when a minimal two-group contract is preferable to the
larger university starter.

## Current bundled counts

Current validation reports:

| Bundle | Groups | Leaf services | Roles | Synthetic staff accounts | Synthetic customers | Test scenarios |
|---|---:|---:|---:|---:|---:|---:|
| Minimal example | 2 | 1 | 1 | 1 | 1 | 1 |
| University starter | 11 | 7 | 7 | 7 | 3 | 8 |

These values are derived from JSON and are covered by tests. They are not
hardcoded compiler limits.
