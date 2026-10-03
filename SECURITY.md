# Security policy

## Supported versions

Queuewright has no published supported release. `0.1.0-alpha.1` is an
unreleased prerelease, and compatibility is not guaranteed before `1.0.0`.

## Reporting a vulnerability

Use GitHub private vulnerability reporting if the repository's Security page
offers it. Do not include credentials, tenant URLs, customer data, or exploit
details in a public issue. The repository does not define an alternate public
security contact.

## Sensitive-data boundary

Do not commit access tokens, passwords, private keys, package credentials,
customer data, tenant URLs, approval records, runtime evidence, local exports,
or browser drafts. Bundled examples must use fictional `example.invalid`
identities and symbolic resource identifiers.

The active product has these enforced boundaries:

- `queuewright` reads explicit local bundles and emits local symbolic plans;
- `queuewright/studio` binds only to `127.0.0.1`, validates loopback hosts and
  origins, accepts bounded JSON, and holds no server-side project state;
- Studio browser drafts are unencrypted local IndexedDB records. Clear site
  data for `127.0.0.1:5173` to remove them;
- Blueprint V2 rejects `applied` and `verified` states because the active
  product has no external evidence source.

`experimental/connected_control` is a separate, transport-injected package.
Its credential, connection, evidence, and ledger primitives are not imported
by the CLI, API, or Studio client and do not constitute a live tenant
integration.
