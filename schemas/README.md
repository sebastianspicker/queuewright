# JSON Schemas

| Schema | Purpose |
|---|---|
| `queuewright-profile.schema.json` | Offline profile bundle |
| `queuewright-desired-state.schema.json` | Symbolic desired state |
| `queuewright-project.schema.json` | V1 Studio project |
| `queuewright-project-v2.schema.json` | Blueprint V2 project |
| `zammad-connection.schema.json` | Future connected-control runtime input |

The profile and desired-state schemas accept versions `1.0` and `1.1`.
Version `1.1` adds nested container groups.

The schemas validate document shape for editors and external tooling. Python
validation remains authoritative for cross-document references, service-tree
reachability, cycles, exact resource ownership, feature dependencies, URL
rejection, and sensitive-setting rejection.

Offline Blueprint V2 documents may use `decision_required`, `ready`, or
`blocked`. The validator rejects `applied` and `verified` because those states
require external evidence.

The connection schema is not accepted by the CLI or Studio. It belongs to the
unwired `queuewright_control` package and may contain runtime secrets.
