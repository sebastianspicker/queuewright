# Queuewright Studio

Queuewright Studio is a React application for editing local Zammad
configuration projects. It uses a loopback Python service for validation,
V1 plan compilation, V1-to-V2 migration, and V2 graph compilation.

Studio has no tenant URL field, credential input, discovery request, or apply
operation.

## Workflow

The interface has eight steps:

1. Start: create, open, or import a local project.
2. Organization: record operating context and ownership.
3. Services: edit one rooted tree of organizational units and ticket-bearing
   services.
4. Access: review organizations, synthetic populations, roles, and leaf-level
   access.
5. Policies: configure fields, views, support tooling, automation, reporting,
   handoff, and review controls.
6. Governance: record completion and delivery status for each capability
   family.
7. Readiness: review synthetic test coverage, unresolved decisions, manual
   work, unsupported areas, and the current graph.
8. Review: validate and download the V1 project, V2 Blueprint, profile,
   desired state, symbolic plan, and graph.

Capability accounting records whether a configuration area is automated,
manual, verification-only, or unsupported. It does not imply a Zammad API
implementation.

## Create, open, and import projects

The start screen provides three ways to begin:

- Select `Blank project` to create an empty project.
- Select `University template` to load the bundled example.
- Select `Import` and choose one or two JSON files.

The create actions require the loopback compiler service. Projects saved in the
browser appear under `Projects in this browser`; select one to reopen it.

Import accepts any one of these forms:

- one Blueprint V2 document with `project_schema_version` set to `2.0`;
- one V1 project document with `project_schema_version` set to `1.0`;
- one object containing both `profile` and `manifest`;
- a profile JSON file and its manifest JSON file selected together.

Each imported file must be no larger than 2 MiB. Studio validates and compiles
imported data through the loopback service. It derives the alternate project
representation so the V1 and V2 editors remain available. Invalid stored
projects are quarantined instead of being opened.

## Runtime

Studio consists of two processes:

```text
browser at 127.0.0.1:5173
  -> Vite proxy for /api/v1 and /api/v2
  -> Python service at 127.0.0.1:8765
```

Vite uses strict loopback binding and an explicit filesystem allowlist. The
Python service rejects non-loopback construction, validates `Host` and
`Origin`, accepts exact `application/json` POST bodies up to 2 MiB, and returns
`Cache-Control: no-store`.

The service exposes:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Service health |
| `GET` | `/api/v1/catalog` | V1 feature catalog |
| `POST` | `/api/v1/import-bundle` | Validate a profile and manifest and create a V1 project |
| `POST` | `/api/v1/compile-project` | Validate a V1 project and compile local artifacts |
| `POST` | `/api/v2/migrate-project` | Convert a valid V1 project to Blueprint V2 |
| `POST` | `/api/v2/compile-project` | Validate Blueprint V2 and compile its graph |

Other paths and methods return structured JSON errors.

## Project formats

A V1 project contains project metadata, a profile, a desired-state manifest,
resource ownership, and feature state.

A Blueprint V2 project contains exactly:

```text
project_schema_version
id
name
target_schema_version
workbook
extensions
bundle
```

The `bundle` retains the validated V1 profile, manifest, ownership map, and
feature state. The workbook contains organization context plus compiler-derived
service, policy, capability, and test views.

Offline projects may record `decision_required`, `ready`, or `blocked`.
`applied` and `verified` are rejected because those states require external
evidence that Studio cannot provide.

The compiler rejects missing or extra ownership entries, unknown owners,
disabled dependencies, URLs, credential-shaped keys, non-JSON values, and
changes to derived workbook sections.

## Browser storage and downloads

Studio stores projects in IndexedDB database `queuewright-studio`, version 3.
It uses separate stores for V1 projects, V2 Blueprints, and the active project
identifier.

The current interface has no deletion control. Clear site data for
`127.0.0.1:5173` to remove stored projects.

Downloads remain disabled until both the V1 plan and V2 graph compile for the
current project revision. Compilation returns local JSON artifacts only.

## Run locally

From the repository root:

```bash
python3 -m queuewright_studio
```

In another terminal:

```bash
cd studio-ui
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`.

## Testing

Run frontend unit tests and the TypeScript build:

```bash
cd studio-ui
npm run test
npm run build
```

Run the browser test:

```bash
npm run test:e2e
```

Playwright starts both loopback processes and requires ports `5173` and `8765`
to be available.

Backend API and boundary tests are part of the Python suite:

```bash
python3 -m unittest discover -s tests -v
```

## Related files

| Path | Purpose |
|---|---|
| `studio-ui/src/api.ts` | Frontend HTTP boundary |
| `studio-ui/src/studio-state.tsx` | Project and compilation state |
| `studio-ui/src/storage.ts` | IndexedDB persistence |
| `queuewright_studio/service.py` | Loopback service and endpoint dispatch |
| `queuewright/blueprint.py` | V2 validation, migration, and graph compilation |
| `studio/catalog/features.json` | V1 feature catalog |
| `studio/catalog/capabilities.json` | Capability accounting |
| `schemas/queuewright-project.schema.json` | V1 project schema |
| `schemas/queuewright-project-v2.schema.json` | V2 project schema |
