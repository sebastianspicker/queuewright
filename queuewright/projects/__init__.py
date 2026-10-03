"""Canonical project models, V1 migration adapter, and graph compilation.

This package is pure domain logic: it raises :class:`ProjectError` and never
knows about HTTP routes, status codes, or response envelopes.
"""

from .bundle import validate_bundle
from .errors import ProjectError
from .graph import compile_v1_snapshot, compile_v2_project
from .registry import load_capabilities, load_feature_catalog
from .v1 import (
    V1Snapshot,
    compiled_v1_artifacts,
    is_v1_project,
    new_v1_project,
    validate_v1_project,
)
from .v2 import (
    migrate_v1_project,
    migrate_v1_snapshot,
    validate_exported_v2_project,
    validate_v2_project,
)

__all__ = [
    "ProjectError",
    "V1Snapshot",
    "compile_v1_snapshot",
    "compile_v2_project",
    "compiled_v1_artifacts",
    "is_v1_project",
    "load_capabilities",
    "load_feature_catalog",
    "migrate_v1_project",
    "migrate_v1_snapshot",
    "new_v1_project",
    "validate_bundle",
    "validate_exported_v2_project",
    "validate_v1_project",
    "validate_v2_project",
]
