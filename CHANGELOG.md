# Changelog

Notable public changes are recorded in this file. Queuewright intends to use
[Semantic Versioning](https://semver.org/) for public releases.

## [0.1.0-alpha.1] - Unreleased

Initial offline compiler and Studio prerelease. See the
[release notes](docs/releases/0.1.0-alpha.1.md) for its included capabilities,
safety boundary, and limitations.

### Changed

- `python -m queuewright_studio` now delegates to `queuewright studio` and
  rejects unknown arguments.
- Corrupt packaged registries now raise `ConfigurationError` ("feature
  registry ...").
- The Studio API smoke script is replaced by real-HTTP tests.

### Fixed

- Profile validation is total: wrongly shaped values (for example a list where
  a key is expected) raise `ConfigurationError` instead of `TypeError`, so the
  CLI reports a usage error rather than a traceback.

### Removed

- The facade modules `queuewright.profile`, `queuewright.compiler`,
  `queuewright.blueprint`, and `queuewright_studio.service`. Use `queuewright`,
  `queuewright.configuration`, `queuewright.projects`, or `queuewright.studio`.
- Custom feature-catalog injection.
- Unused `queuewright.contracts` helpers `safe_json_failure` and `schema_path`;
  `example_path` moved to `queuewright.examples`.
