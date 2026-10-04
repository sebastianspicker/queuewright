# Queuewright

Queuewright validates local JSON descriptions of Zammad configuration and
compiles deterministic symbolic plans for review. Queuewright Studio edits the
same model through a loopback-only browser application.

The project is an unpublished alpha. File formats and Studio workflows may
change before `1.0.0`.

Queuewright does not discover tenants, read credentials, make outbound
requests, or apply configuration. Plans, graphs, and `ready` states are local
design artifacts, not evidence of tenant changes.

## Capabilities

- validate offline profile and desired-state bundles;
- compile dependency-ordered symbolic plans;
- import V1 Studio projects and migrate them to canonical Blueprint V2;
- edit, validate, and export local projects in Queuewright Studio;
- build a client-only Studio demo from bundled fictional data.

The repository also contains an isolated experimental connected-control
package. It supplies transport-injected primitives, not a live Zammad adapter.

## Requirements

- Python 3.11 or newer;
- Node.js 22.12 or newer and npm 10 or newer for Studio.

## Quick start

Run these commands from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[dev]'
npm --prefix studio-ui ci
.venv/bin/python -m queuewright self-test
```

Validate and compile the minimal bundled profile:

```bash
.venv/bin/python -m queuewright validate \
  queuewright/examples/minimal/profile.json
.venv/bin/python -m queuewright plan \
  queuewright/examples/minimal/profile.json
```

Use `--output /path/to/new-plan.json` with `plan` to write a new file. The
CLI refuses sensitive paths, input paths, non-JSON destinations, and existing
output files. See [Configuration](docs/CONFIGURATION.md) for bundle structure,
validation authority, and customization rules.

## Queuewright Studio

Start the API and frontend in separate terminals:

```bash
.venv/bin/python -m queuewright studio
```

```bash
npm --prefix studio-ui run dev
```

Open `http://127.0.0.1:5173`. The API listens on
`http://127.0.0.1:8765`. See the [Studio guide](docs/STUDIO.md) for the
runtime, project formats, local storage, endpoints, and static demo.

## Components

| Path | Purpose | Runtime and lifecycle | Documentation |
| --- | --- | --- | --- |
| `queuewright/` | Active contracts, configuration, planning, projects, CLI, and Studio API | Installable Python package; `queuewright.__all__` is the Python API | [Architecture](docs/ARCHITECTURE.md) |
| `queuewright_studio/` | Module-entry shim for `python -m queuewright_studio` | Removed at the first tagged release | [Studio guide](docs/STUDIO.md) |
| `studio-ui/` | Queuewright Studio browser client | Private Node package; developed and built independently | [Studio UI](studio-ui/README.md) |
| `experimental/connected_control/` | Transport-injected connected-control primitives | Separately installed experimental Python package | [Connected control](experimental/connected_control/README.md) |
| `queuewright/contracts/schemas/` | Packaged JSON document shapes | Consumed by the active package and external tooling | [Schema notes](queuewright/contracts/schemas/README.md) |
| `queuewright/examples/` | Packaged fictional profiles and projects | CLI inputs and Studio starter data | [Examples](queuewright/examples/README.md) |

The active Python dependency direction is
`contracts <- configuration <- planning <- projects <- studio`. Blueprint V2
is canonical; V1 remains a compatibility input. The
[architecture guide](docs/ARCHITECTURE.md) defines the full boundaries.

## Development and verification

The complete active-product gate is:

```bash
bash scripts/verify
```

It runs Ruff, architecture policy, Python self-tests, repository and ignore policy, Studio tests and builds
(the build type-checks), and Python package archive validation. It uses
`$PYTHON`, else `.venv/bin/python`, else `python3`. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the connected-control lane and focused
commands.

Contributor rules are in [CONTRIBUTING.md](CONTRIBUTING.md). Release and
security procedures are in [RELEASING.md](RELEASING.md) and
[SECURITY.md](SECURITY.md).

## Static demo

The [Studio demo](https://sebastianspicker.github.io/queuewright-zammad/) is a
client-only GitHub Pages build. It uses bundled fictional data and has no API,
persistence, tenant connection, or configuration-apply capability.

## License

Queuewright is licensed under the [MIT License](LICENSE).
