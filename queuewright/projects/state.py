"""Resource ownership and feature state: strict validation and draft normalization.

Strict validation is the portable contract every V1 project and every canonical
bundle must satisfy. Draft normalization first rebuilds ownership and feature
state against the current bundle, keeping authored values that still apply, and
then runs strict validation. The two paths deliberately report different faults
with different messages: draft entries have no locked-feature check, and their
safety faults keep the historical ``"<path> <message>"`` wording.
"""

from __future__ import annotations

import copy
from typing import Any

from ..contracts.safety import SafeJsonError, validate_safe_json
from .errors import ProjectError
from .ownership import (
    allowed_owners,
    default_resource_ownership,
    dependency_closure,
    enabled_features,
    resource_ids,
)

FEATURE_STATE_FIELDS = {"enabled", "settings"}
FEATURE_STATE_MESSAGE = "feature state requires boolean enabled and object settings"
OWNER_MESSAGE = "owner must be core, custom, or a catalog feature ID"


def is_feature_state_entry(state: Any) -> bool:
    """Return whether a feature state entry has boolean enabled and object settings."""
    return (
        isinstance(state, dict)
        and set(state) == FEATURE_STATE_FIELDS
        and state["enabled"].__class__ is bool
        and isinstance(state["settings"], dict)
    )


def validate_studio_state(
    profile: dict[str, Any],
    manifest: dict[str, Any],
    ownership: Any,
    feature_state: Any,
    features: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Validate ownership and feature state once for V1 and V2 callers."""
    _validate_ownership(profile, manifest, ownership, features)
    features_by_id = {feature["id"]: feature for feature in features}
    _validate_feature_state(feature_state, features_by_id)
    _validate_enabled_dependencies(feature_state, features_by_id)
    _validate_resource_owner_features(ownership, feature_state, features_by_id)
    return copy.deepcopy(ownership), copy.deepcopy(feature_state)


def _validate_ownership(
    profile: dict[str, Any],
    manifest: dict[str, Any],
    ownership: Any,
    features: list[dict[str, Any]],
) -> None:
    if not isinstance(ownership, dict):
        raise ProjectError(
            "resource_ownership must be an object", path="resource_ownership", kind="malformed"
        )
    expected = resource_ids(profile, manifest)
    missing = expected - set(ownership)
    extra = set(ownership) - expected
    if missing:
        raise ProjectError(
            f"missing resource ownership: {min(missing)}",
            path="resource_ownership",
            kind="malformed",
        )
    if extra:
        raise ProjectError(
            f"unknown resource ownership: {min(extra)}",
            path="resource_ownership",
            kind="malformed",
        )
    owners = allowed_owners(features)
    invalid = sorted(
        resource
        for resource, owner in ownership.items()
        if not isinstance(owner, str) or owner not in owners
    )
    if invalid:
        raise ProjectError(OWNER_MESSAGE, path=f"resource_ownership.{invalid[0]}", kind="malformed")


def _validate_feature_state(
    feature_state: Any, features_by_id: dict[str, dict[str, Any]]
) -> None:
    if not isinstance(feature_state, dict) or set(feature_state) != set(features_by_id):
        raise ProjectError(
            "feature_state must define every catalog feature exactly",
            path="feature_state",
            kind="malformed",
        )
    for feature_id in sorted(features_by_id):
        state = feature_state[feature_id]
        if not is_feature_state_entry(state):
            raise ProjectError(
                FEATURE_STATE_MESSAGE, path=f"feature_state.{feature_id}", kind="malformed"
            )
        if features_by_id[feature_id]["locked"] and not state["enabled"]:
            raise ProjectError(
                "locked features must remain enabled", path=f"feature_state.{feature_id}.enabled"
            )
        try:
            validate_safe_json(state["settings"], f"feature_state.{feature_id}.settings")
        except SafeJsonError as error:
            raise ProjectError(error.message, path=error.path, kind="malformed") from error


def _validate_enabled_dependencies(
    feature_state: dict[str, dict[str, Any]], features_by_id: dict[str, dict[str, Any]]
) -> None:
    for feature_id in sorted(features_by_id):
        if not feature_state[feature_id]["enabled"]:
            continue
        disabled_dependencies = sorted(
            dependency
            for dependency in features_by_id[feature_id]["dependencies"]
            if not feature_state[dependency]["enabled"]
        )
        if disabled_dependencies:
            raise ProjectError(
                f"enabled feature requires enabled dependency: {disabled_dependencies[0]}",
                path=f"feature_state.{feature_id}.enabled",
            )


def _validate_resource_owner_features(
    ownership: dict[str, str],
    feature_state: dict[str, dict[str, Any]],
    features_by_id: dict[str, dict[str, Any]],
) -> None:
    for resource in sorted(ownership):
        owner = ownership[resource]
        if owner in features_by_id and not feature_state[owner]["enabled"]:
            raise ProjectError(
                f"resource owner feature must be enabled: {owner}",
                path=f"resource_ownership.{resource}",
            )


def normalize_draft_state(
    profile: dict[str, Any],
    manifest: dict[str, Any],
    ownership: Any,
    feature_state: Any,
    features: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Normalize draft ownership and feature state against the current bundle."""
    normalized_ownership = _normalize_resource_ownership(profile, manifest, ownership, features)
    normalized_state = _normalize_feature_state(feature_state, normalized_ownership, features)
    return validate_studio_state(
        profile, manifest, normalized_ownership, normalized_state, features
    )


def _normalize_resource_ownership(
    profile: dict[str, Any],
    manifest: dict[str, Any],
    previous: Any,
    features: list[dict[str, Any]],
) -> dict[str, str]:
    if not isinstance(previous, dict):
        raise ProjectError("bundle resource_ownership must be an object")
    normalized = default_resource_ownership(profile, manifest)
    owners = allowed_owners(features)
    for resource, owner in previous.items():
        if resource not in normalized:
            continue
        if not isinstance(owner, str) or owner not in owners:
            raise ProjectError(OWNER_MESSAGE, path=f"resource_ownership.{resource}")
        normalized[resource] = owner
    return normalized


def _normalize_feature_state(
    previous: Any, ownership: dict[str, str], features: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if not isinstance(previous, dict):
        raise ProjectError("bundle feature_state must be an object")
    features_by_id = {feature["id"]: feature for feature in features}
    enabled_by_default = enabled_features(features, ownership)
    normalized = {
        feature_id: {
            "enabled": feature_id in enabled_by_default,
            "settings": copy.deepcopy(feature["settings"]),
        }
        for feature_id, feature in features_by_id.items()
    }
    for feature_id, state in previous.items():
        if feature_id not in features_by_id:
            continue
        _validate_draft_entry(feature_id, state)
        normalized[feature_id] = copy.deepcopy(state)
    enabled = {feature_id for feature_id, state in normalized.items() if state["enabled"]}
    enabled = dependency_closure(enabled | enabled_by_default, features)
    for feature_id, state in normalized.items():
        state["enabled"] = feature_id in enabled
    return normalized


def _validate_draft_entry(feature_id: str, state: Any) -> None:
    if not is_feature_state_entry(state):
        raise ProjectError(FEATURE_STATE_MESSAGE, path=f"feature_state.{feature_id}")
    try:
        validate_safe_json(state["settings"], f"feature_state.{feature_id}.settings")
    except SafeJsonError as error:
        raise ProjectError(f"{error.path} {error.message}") from error
