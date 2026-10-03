# Contributing

Queuewright accepts focused changes that preserve its offline safety and
compatibility contracts. Read the [architecture guide](docs/ARCHITECTURE.md)
before moving code or changing a JSON or HTTP interface.

## Setup

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[dev]'
npm --prefix studio-ui ci
```

Python 3.11 or newer is required. Studio requires Node.js 22.12 or newer and
npm 10 or newer.

## Where code belongs

- `queuewright/contracts/`: schemas, catalogs, canonical JSON, catalog paths,
  and safe-JSON rules. No imports from other layers.
- `queuewright/configuration/`: profile and desired-state loading and
  validation rules.
- `queuewright/planning/`: symbolic-plan compilation and inventory.
- `queuewright/projects/`: Blueprint V2, the V1 adapter, shared bundle checks
  (`bundle.py`), and project compilation. Pure domain logic that raises `ProjectError`; no HTTP concepts.
- `queuewright/studio/`: route table, error envelopes, and status mapping in
  `routes.py`; loopback transport in `server.py`.
- `queuewright_studio/` is only a module-entry shim; do not add behavior.
- `studio-ui/src/`: `api` (fetch), `persistence` (storage), `editor`
  (state and `editor/model`), and `app`, `components`, `screens` for
  presentation.

Do not import an underscore-prefixed name from another subpackage.

## Change rules

1. Keep the active Python layers one-way: `contracts`, `configuration`,
   `planning`, `projects`, then `studio`.
2. Keep active packages independent from `experimental/connected_control` and
   free of outbound networking, credential discovery, and tenant mutation.
3. Treat Blueprint V2 as canonical. Preserve V1 import, validation, and
   migration unless an explicit contract change replaces them. The public
   Python API is `queuewright.__all__`.
4. Keep browser transport in `studio-ui/src/api/client.ts`, browser storage in
   `studio-ui/src/persistence/`, and presentation code behind the editor seam.
5. Add or update behavior tests with contract changes. Update schemas,
   examples, package data, and documentation when their contract changes.
6. Do not add credentials, tenant data, browser exports, or machine-local
   state. Bundled data must remain fictional.

## Checks

Run the active verification contract from the repository root:

```bash
bash scripts/verify
```

For a connected-control change, install and test that package separately:

```bash
python3 -m pip install ./experimental/connected_control
python3 -m unittest discover -s experimental/connected_control/tests \
  -p 'test_*.py' -v
python3 scripts/verify_control_package.py
```

`scripts/verify` includes the configured Python linter, architecture and
repository policy, Python tests (including real-HTTP Studio tests), Studio
tests, TypeScript builds, and package archive checks. It runs Python lanes with
`$PYTHON`, else `.venv/bin/python`, else `python3`. Focused frontend commands:

```bash
npm --prefix studio-ui run typecheck
npm --prefix studio-ui run test
```

The repository does not configure a separate formatter, Python type checker,
or frontend linter.

Visible Studio changes also require manual desktop and mobile review,
keyboard and focus checks, zoom and clipping checks, and review of loading,
empty, error, and unavailable-service states.

Report every skipped check with its error and affected scope. Local checks do
not prove tenant behavior, hosted API behavior, cross-browser compatibility,
or accessibility conformance.

## Performance checks

Run `python3 scripts/benchmark_compilation.py` for deterministic university
projects with progressively deeper container hierarchies. The command reports
Python/platform versions, a warmup, repeated timing ranges, canonical hashes,
and full versus editor response sizes. Compare runs on the same machine and
interpreter. Timing is diagnostic; tests enforce ordering, output equality,
and bounded traversal behavior without machine-dependent time limits.
