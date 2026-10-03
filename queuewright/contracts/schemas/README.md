# JSON Schemas

| Schema | Purpose |
|---|---|
| `queuewright-profile.schema.json` | Offline profile bundle |
| `queuewright-desired-state.schema.json` | Symbolic desired state |
| `queuewright-project.schema.json` | V1 Studio project |
| `queuewright-project-v2.schema.json` | Blueprint V2 project |
| `queuewright-editor-compile.schema.json` | Compact editor compilation response |

The profile and desired-state schemas accept versions `1.0` and `1.1`.
Version `1.1` adds nested container groups.

The schemas validate document shape for editors and external tooling. V2 also
applies the portable safe-JSON contract recursively to editable organization
data, extensions, and compiler-owned mirrors: strings cannot contain URLs and
credential-shaped property names are rejected. Python validation remains
authoritative for cross-document references, service-tree reachability, cycles,
exact resource ownership, feature dependencies, finite-number checks, and
registry-derived metadata values.

Offline Blueprint V2 documents may use `decision_required`, `ready`, or
`blocked`. The validator rejects `applied` and `verified` because those states
require external evidence.

Python bounds JSON container nesting to 64 levels before recursive processing.
HTTP requests exceeding parser numeric or nesting limits receive an
`invalid_json` error. This resource limit is enforced in Python; the recursive
JSON Schemas describe value shape.

Python compilation additionally enforces fixed budgets of 10,000 operations,
100,000 dependency references, 8 MiB of dependency identifiers, 1,000,000
service-derivation membership checks, and an 8 MiB derived service projection.
These expansion limits are semantic runtime constraints rather than JSON
Schema shape constraints.

The active schemas describe offline inputs and compiler output. The connection schema belongs only
to the isolated experimental connected-control package and is not shipped in
the active wheel.
