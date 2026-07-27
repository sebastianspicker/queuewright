# Security policy

## Supported version

Security fixes target the latest source-release candidate. Interfaces may
change while the project remains below `1.0.0`.

## Reporting a vulnerability

Use GitHub private vulnerability reporting when it is available. Do not open a
public issue containing credentials, tenant URLs, customer data, or exploit
details.

If private reporting is unavailable, open a minimal public issue requesting a
private contact channel. Include no sensitive technical details.

## Data boundary

Do not commit:

- access tokens, OAuth secrets, passwords, private keys, or package-manager
  credentials;
- `.local/`, `.env`, key files, or secret-bearing JSON;
- customer data, ticket exports, tenant URLs, or production snapshots;
- approval records, runtime evidence, or connected-control credentials.

Reusable profiles must use fictional `example.invalid` identities and
symbolic resource identifiers. Human-readable labels still require review
because schemas cannot identify every sensitive value.

## Studio storage

Queuewright Studio stores V1 and V2 drafts in browser IndexedDB for
`http://127.0.0.1:5173`. The current interface does not provide per-draft or
clear-all deletion.

Do not enter credentials, tenant URLs, live snapshots, approval records, or
personal data. To remove local drafts, clear site data for
`127.0.0.1:5173` in the browser profile used for Studio.

## Runtime boundary

- `queuewright` validates local files and emits symbolic plans. It has no
  network client or tenant mutation command.
- `queuewright_studio` binds to `127.0.0.1`, validates JSON in memory, and has
  no credential or tenant connection interface.
- `queuewright_control` is an experimental library with injected transports.
  It is not exposed by the CLI or Studio and includes no Zammad HTTP adapter.
- Plans, graphs, and `ready` states are not authorization or evidence of a
  tenant change.
