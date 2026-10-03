"""Version-independent bundle and header concepts shared by V1 and V2 projects."""

from __future__ import annotations

import re
from typing import Any

from ..configuration import validate_loaded_profile
from ..errors import ConfigurationError
from .errors import ProjectError

PROJECT_ID = re.compile(r"^[a-z][a-z0-9_-]*$")
HEADER_TEXT_FIELDS = ("id", "name", "target_schema_version")
BUNDLE_FIELDS = {"profile", "manifest", "resource_ownership", "feature_state"}
PROJECT_FIELDS = {"project_schema_version", *HEADER_TEXT_FIELDS, *BUNDLE_FIELDS}


def header_violation(project: dict[str, Any], version: str) -> tuple[str, str] | None:
    """Return the first ``(field, rule)`` breaking the shared project header contract.

    ``rule`` is ``"version"``, ``"text"``, or ``"pattern"``. V1 and V2 callers
    report the same violation with their own historical wording.
    """
    if project.get("project_schema_version") != version:
        return "project_schema_version", "version"
    for field in HEADER_TEXT_FIELDS:
        if not isinstance(project.get(field), str) or not project[field].strip():
            return field, "text"
    if PROJECT_ID.fullmatch(project["id"]) is None:
        return "id", "pattern"
    return None


def require_matching_versions(
    target_schema_version: Any, profile: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """Reject project metadata that disagrees with its profile and manifest."""
    if (
        target_schema_version != profile.get("schema_version")
        or target_schema_version != manifest.get("schema_version")
    ):
        raise ProjectError("project metadata must match its profile and manifest")


def validate_bundle(loaded: dict[str, Any]) -> dict[str, Any]:
    """Validate a profile and manifest pair and return its profile summary."""
    try:
        return validate_loaded_profile(loaded)
    except ConfigurationError as error:
        raise ProjectError(str(error)) from error
