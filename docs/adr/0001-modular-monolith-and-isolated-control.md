# ADR 0001: Modular monolith and isolated control

## Status

Accepted.

## Decision

Keep the offline compiler, project model, and loopback Studio API in one
installable `queuewright` package with explicit internal layers. Use Blueprint
V2 as the canonical project model and retain V1 only as a validation and
migration adapter.

Keep connected-control primitives in `experimental/connected_control` as a
separately installed and tested package. It must not import active packages,
and active packages must not import it.

## Consequences

The active product remains easy to install and verify without a tenant or
credential dependency. Layer checks make internal ownership visible. V1 callers
remain supported through a single adapter. Connected-control work can evolve
without adding tenant or credential behavior to the offline product.
