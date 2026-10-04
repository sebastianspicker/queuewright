# Queuewright connected control (experimental)

This directory is a separately installed experimental Python package. It
contains transport-injected primitives for connection identity, credentials,
operation policy, previews, evidence, recovery, encrypted local ledgers, and a
loopback dispatcher.

It has no console entry point, product integration, default network transport,
or Zammad adapter. The active Queuewright CLI, API, and Studio client do not
import it. Unit tests demonstrate the primitives with injected transports; they
do not demonstrate tenant operation.

The package requires Python 3.11 or newer and pins `cryptography==50.0.2`.
Install and test it from the repository root:

```bash
python3 -m pip install ./experimental/connected_control
python3 -m unittest discover -s experimental/connected_control/tests \
  -p 'test_*.py' -v
```

The ledger fully authenticates the audit chain and replays its derived
operational facts when it opens. After that, it may reuse an in-memory-only
verified snapshot while the protected anchor, SQLite connection counters and
schema versions, exact schema definitions, and owner-controlled file identity
all remain unchanged. Each write takes a SQLite immediate transaction before
preflight, validates its audit tail and affected operational rows before
commit, and reconciles the protected anchor under a second write lock. Any
unexplained change, nonstandard schema, temporary schema object, rollback, or
anchor update failure discards the fast path and requires a complete replay.
`verify_audit_chain()` always scans the current chain.

Run the comparable append benchmark from the repository root. It creates and
removes a separate temporary ledger for each sample and reports all samples
plus median, minimum, and maximum durations; it has no wall-clock assertion:

```bash
PYTHONPATH=experimental/connected_control .venv/bin/python \
  experimental/connected_control/benchmarks/benchmark_ledger.py
```

Lock rows remain lease and fencing coordination state rather than authenticated
operational facts. The audit chain records lock lifecycle events without the
raw fence or expiry. The owner-only ledger file boundary is therefore required
for lock integrity; a full audit replay does not independently authenticate a
legacy lock row.

The packaged `queuewright_control/schemas/zammad-connection.schema.json`
belongs only to this experimental runtime. It is not included in the active
Queuewright wheel. Do not place credentials, tenant URLs, approval records, or
runtime evidence in examples, logs, or repository artifacts.

Repository-wide sensitive-data rules are in
[../../SECURITY.md](../../SECURITY.md).
