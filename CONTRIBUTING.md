# Contributing

Queuewright is an unpublished alpha. Keep changes focused and preserve the
offline boundary unless the change is explicitly scoped to
`queuewright_control`.

## Development setup

The CLI and Studio service require Python 3.11 or newer. The complete Python
test suite also requires the pinned connected-control dependency:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --requirement requirements-control.txt
```

The frontend requires Node.js 22.12 or newer and npm 10 or newer:

```bash
cd studio-ui
npm ci
```

## Change requirements

1. Keep organization-specific policy in JSON profiles and templates.
2. Keep `queuewright` and `queuewright_studio` free of outbound networking,
   credential discovery, and tenant mutation.
3. Preserve exact schema, API, and file-format contracts unless the change
   includes tests and migration guidance.
4. Add tests for behavior and failure modes.
5. Update paths, commands, examples, and screenshots affected by the change.
6. Keep secrets, customer data, local exports, browser profiles, caches, and
   machine-specific state out of the change.

## Testing

Run the Python gates from the repository root:

```bash
python3 -m queuewright self-test
python3 -m unittest discover -s tests -v
python3 scripts/verify_repo.py
```

Run the frontend gates from `studio-ui/`:

```bash
npm run test
npm run build
npm run test:e2e
```

`npm run build` performs TypeScript checking. The repository does not configure
a separate Python linter, formatter, or static type checker.

If a gate cannot run, record the command, error, and affected scope. Do not
report a narrower check as proof for an unrun broader gate.

## Pull requests

- Describe the user-visible or contract-level change.
- List the checks that passed and the checks that were skipped.
- Distinguish local validation from tenant behavior.
- Include current UI captures only when the corresponding browser flow passed.
- Do not include personal paths, private URLs, credentials, or unrelated
  desktop content in captures.
- Update `CHANGELOG.md` only for changes relevant to a public release.
