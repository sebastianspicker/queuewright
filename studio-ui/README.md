# Queuewright Studio UI

`studio-ui` is the private React, TypeScript, and Vite package for Queuewright
Studio. It is built independently but requires the active Python loopback API
for normal local use.

Node.js 22.12 or newer and npm 10 or newer are required.

## Local development

From the repository root:

```bash
npm --prefix studio-ui ci
python3 -m queuewright studio
```

In another terminal:

```bash
npm --prefix studio-ui run dev
```

Open `http://127.0.0.1:5173`. Vite binds that exact loopback port and proxies
`/api/v1` and `/api/v2` to `http://127.0.0.1:8765`.

## Structure

`src/` is organized as `api` (the only fetch surface), `app`, `components`,
`contracts`, `data` (bundled fictional data), `editor` (state; `editor/model`
is the model surface), `persistence` (the only browser-storage surface),
`screens`, and `styles`. Presentation code (`app`, `components`, `screens`)
reaches the API and storage only through the editor.

## Commands

```bash
npm --prefix studio-ui run typecheck
npm --prefix studio-ui run test
npm --prefix studio-ui run test:watch
npm --prefix studio-ui run build
npm --prefix studio-ui run build:demo
```

`typecheck` runs `tsc -b`, which also type-checks tests through
`tsconfig.test.json`. `build` performs the same TypeScript build before Vite.
`build:demo` sets `VITE_STATIC_DEMO=true`, uses the `/queuewright-zammad/` base
path, and produces a client-only build from bundled fictional data. The static
demo has no API or browser persistence.

Keep all browser fetches in `src/api/client.ts`, browser storage in
`src/persistence/`, and UI composition behind the editor seam. See the
[Studio guide](../docs/STUDIO.md) for project formats, HTTP routes, persistence,
and manual interface checks.
