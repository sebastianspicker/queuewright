# Changelog

Notable public changes are recorded in this file. Queuewright intends to use
[Semantic Versioning](https://semver.org/) for public releases.

## [Unreleased]

### Changed

- Add Blueprint V2 migration, validation, and graph compilation.
- Add the eight-step local Studio workflow.
- Add the university starter and minimal example profile.
- Add the experimental connected-control package and its pinned cryptography
  dependency.
- Store local Studio projects in IndexedDB.

### Known limitations

- Browser validation and final-candidate screenshot recapture remain open.

## [0.1.0-alpha.1] - Unreleased

### Included

- Dependency-free profile validation and deterministic symbolic plans.
- Eight-step local Queuewright Studio source application.
- Blueprint V2 migration, ownership validation, and capability graphs.
- Neutral university and minimal example profiles.
- Transport-injected connected-mode primitives that are not wired to the CLI
  or Studio.

### Security boundary

- Offline packages do not load credentials, tenant origins, or environment
  values.
- Studio services bind to loopback and compile JSON in memory.
- Local secrets, machine-specific state, exports, browser output, and ledgers
  are excluded from the intended public file set.

### Alpha limitations

- No live Zammad discovery, HTTP adapter, or apply path.
- No package publication or hosted Studio.
- File formats and UI workflows may change before `1.0.0`.
