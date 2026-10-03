"""The portable Studio V1 project model: header, validated snapshots, and artifacts."""

from __future__ import annotations

import copy
from typing import Any, NamedTuple

from ..contracts.json import canonical_sha256
from .bundle import (
    PROJECT_FIELDS,
    header_violation,
    require_matching_versions,
    validate_bundle,
)
from .errors import ProjectError
from .ownership import default_resource_ownership, enabled_features
from .registry import load_features
from .state import validate_studio_state

PROJECT_SCHEMA_VERSION = "1.0"


class V1Snapshot(NamedTuple):
    """A validated V1 project with its detached bundle and profile summary."""

    project: dict[str, Any]
    loaded: dict[str, Any]
    profile_summary: dict[str, Any]


def is_v1_project(project: Any) -> bool:
    """Return whether a submitted project declares the V1 schema version."""
    return (
        isinstance(project, dict)
        and project.get("project_schema_version") == PROJECT_SCHEMA_VERSION
    )


def new_v1_project(loaded: dict[str, Any]) -> dict[str, Any]:
    """Create the default V1 project for an already validated bundle."""
    profile = loaded["profile"]
    manifest = loaded["manifest"]
    features = load_features()
    ownership = default_resource_ownership(profile, manifest)
    enabled = enabled_features(features, ownership)
    return {
        "project_schema_version": PROJECT_SCHEMA_VERSION,
        "id": f"{profile['profile_key']}-project",
        "name": profile["display_name"],
        "target_schema_version": profile["schema_version"],
        "profile": copy.deepcopy(profile),
        "manifest": copy.deepcopy(manifest),
        "resource_ownership": ownership,
        "feature_state": {
            feature["id"]: {"enabled": feature["id"] in enabled, "settings": feature["settings"]}
            for feature in features
        },
    }


def validate_v1_project(project: Any) -> V1Snapshot:
    """Validate a V1 project and return a detached snapshot of it."""
    if not isinstance(project, dict):
        raise ProjectError("object required", kind="malformed")
    _validate_header(project)
    loaded: dict[str, Any] = {}
    for field in ("profile", "manifest"):
        if not isinstance(project[field], dict):
            raise ProjectError("object required", path=field, kind="malformed")
        loaded[field] = copy.deepcopy(project[field])
    summary = validate_bundle(loaded)
    ownership, feature_state = validate_studio_state(
        loaded["profile"],
        loaded["manifest"],
        project["resource_ownership"],
        project["feature_state"],
        load_features(),
    )
    require_matching_versions(
        project["target_schema_version"], loaded["profile"], loaded["manifest"]
    )
    validated = {**project, "resource_ownership": ownership, "feature_state": feature_state}
    return V1Snapshot(copy.deepcopy(validated), loaded, summary)


def _validate_header(project: dict[str, Any]) -> None:
    missing = PROJECT_FIELDS - set(project)
    unknown = set(project) - PROJECT_FIELDS
    if missing:
        raise ProjectError(f"missing required field: {min(missing)}", kind="malformed")
    if unknown:
        raise ProjectError(f"unsupported field: {min(unknown)}", kind="malformed")
    violation = header_violation(project, PROJECT_SCHEMA_VERSION)
    if violation is None:
        return
    field, rule = violation
    if rule == "version":
        raise ProjectError(
            f"project_schema_version must be {PROJECT_SCHEMA_VERSION}", path=field
        )
    if rule == "text":
        raise ProjectError("non-empty string required", path=field, kind="malformed")
    raise ProjectError("id must be a lowercase safe project key", path=field, kind="malformed")


def compiled_v1_artifacts(snapshot: V1Snapshot, plan: dict[str, Any]) -> dict[str, Any]:
    """Describe the V1 export artifacts for a validated snapshot and its plan."""
    loaded = snapshot.loaded
    profile_key = loaded["profile"]["profile_key"]
    return {
        "artifact_filenames": [
            f"{profile_key}.project.json",
            f"{profile_key}.profile.json",
            f"{profile_key}.desired-state.json",
            f"{profile_key}.plan.json",
        ],
        "hashes": {
            "manifest": canonical_sha256(loaded["manifest"]),
            "plan": plan["plan_hash"],
            "profile": canonical_sha256(loaded["profile"]),
            "project": canonical_sha256(snapshot.project),
        },
        "manifest": loaded["manifest"],
        "plan": plan,
        "profile": loaded["profile"],
        "project": snapshot.project,
        "summary": snapshot.profile_summary,
    }
