# Connected-control package

`queuewright_control` contains experimental primitives for a separate
connected executable. It is not imported by the offline CLI or Studio and does
not include a Zammad HTTP adapter.

The package is tested through injected transports. It defines connection
identity, permission policy, immutable previews, approval, encrypted local
evidence, apply and verification states, rollback, and a loopback dispatcher.
None of these components are available through the current user interfaces.

## Dependency

The encrypted ledger requires:

```text
cryptography==50.0.0
```

Install it through `requirements-control.txt`. The offline CLI and Studio
service do not require this dependency.

## Implemented boundaries

The package enforces:

- canonical HTTPS origins and pinned resolved addresses;
- explicit policy for private, loopback, link-local, and reserved addresses;
- exact method, path, body-field, and permission rules;
- rejection of raw URLs, destructive requests, credential-shaped fields, and
  unknown fields;
- immutable, expiring, one-time previews bound to project, tenant, actor,
  policy, and baseline hashes;
- dependency ordering and cycle rejection;
- durable intent before a write;
- reconciliation and readback after ambiguous responses;
- separate apply and verification states;
- blocking of conflicting runs while recovery is incomplete;
- reverse-order rollback for operations proven applied by the same run;
- a mode `0600` SQLite ledger with AES-GCM encrypted evidence and a keyed audit
  chain;
- numeric-loopback dispatch, bounded sessions, one-time bootstrap, and CSRF
  checks.

The package exports its public types from `queuewright_control/__init__.py`.
The version 1 connection input schema is
[`schemas/zammad-connection.schema.json`](../schemas/zammad-connection.schema.json).
Secret-bearing instances of that schema are runtime inputs and must not be
stored in profiles, Studio projects, logs, or exports.

## Missing integration

A usable connected executable still requires:

- an OS-backed key provider for the target platform;
- certificate-validating HTTP transport with redirect and DNS-rebinding
  controls;
- version-specific Zammad adapters and exact response schemas;
- least-privilege discovery credentials;
- restart and fault-injection testing;
- a user interface for approval, verification, and recovery;
- an independently reviewed scope for each permitted resource type.

The current package must not be described as a live integration. Plans and
graphs produced by the offline compiler are not authorization to change a
tenant.
