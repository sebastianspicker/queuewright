"""Shared validation for the portable Studio V1 bundle state."""

from __future__ import annotations

import copy
import re
from typing import Any

from .errors import ConfigurationError


SENSITIVE_SETTING_NAMES = {
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "env",
    "password",
    "secret",
    "session",
    "token",
}


class StudioContractError(ConfigurationError):
    """A portable Studio project violates its cross-version state contract."""

    def __init__(self, status: int, path: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.path = path
        self.message = message


def _key_parts(key: str) -> set[str]:
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return set(re.findall(r"[a-z0-9]+", snake_case.lower()))


def _validate_safe_scalar(value: Any, path: str) -> bool:
    if value is None or value.__class__ in {bool, int}:
        return True
    if value.__class__ is float:
        if value == value and value not in (float("inf"), -float("inf")):
            return True
        raise StudioContractError(400, path, "settings must contain finite JSON numbers")
    if isinstance(value, str):
        if "://" in value:
            raise StudioContractError(400, path, "settings must not contain URLs")
        return True
    return False


def _validate_safe_mapping(value: dict[Any, Any], path: str) -> None:
    for key, item in value.items():
        if not isinstance(key, str):
            raise StudioContractError(400, path, "settings object keys must be strings")
        parts = _key_parts(key)
        if parts & SENSITIVE_SETTING_NAMES or {"api", "key"} <= parts or {"private", "key"} <= parts:
            raise StudioContractError(400, f"{path}.{key}", "sensitive setting names are forbidden")
        _validate_safe(item, f"{path}.{key}")


def _validate_safe(value: Any, path: str) -> None:
    if _validate_safe_scalar(value, path):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_safe(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        _validate_safe_mapping(value, path)
        return
    raise StudioContractError(400, path, "settings must contain only JSON values")


def resource_ids(profile: dict[str, Any], manifest: dict[str, Any]) -> set[str]:
    """Return the exact resource inventory covered by Studio ownership."""
    identifiers: set[str] = set()

    def add(collection: str, items: list[dict[str, Any]], field: str = "key") -> None:
        identifiers.update(f"{collection}:{item[field]}" for item in items)

    add("groups", manifest["groups"])
    add("organizations", manifest["organizations"])
    add("roles", manifest["roles"])
    add("agents", manifest["users"]["agents"])
    add("customers", manifest["users"]["customers"])
    identifiers.update(f"tags:{tag}" for tag in manifest["tags"])
    for collection in (
        "overviews",
        "macros",
        "checklist_templates",
        "triggers",
        "jobs",
        "report_profiles",
    ):
        add(collection, manifest[collection])
    for collection in (
        "ticket_fields",
        "user_fields",
        "organization_fields",
        "group_fields",
    ):
        add(
            "object_manager_fields",
            manifest["object_manager"][collection],
            "name",
        )
    add("core_workflows", manifest["object_manager"]["core_workflows"])
    add("uat_scenarios", profile["uat"]["scenarios"])
    return identifiers


def validate_studio_state(
    profile: dict[str, Any],
    manifest: dict[str, Any],
    ownership: Any,
    feature_state: Any,
    catalog: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Validate ownership and feature state once for V1 and V2 callers."""
    _validate_ownership(profile, manifest, ownership, catalog)
    catalog_by_id = {feature["id"]: feature for feature in catalog}
    _validate_feature_state(feature_state, catalog_by_id)
    _validate_feature_dependencies(ownership, feature_state, catalog_by_id)
    return copy.deepcopy(ownership), copy.deepcopy(feature_state)


def _validate_ownership(profile: dict[str, Any], manifest: dict[str, Any], ownership: Any, catalog: list[dict[str, Any]]) -> None:
    if not isinstance(ownership, dict):
        raise StudioContractError(
            400,
            "resource_ownership",
            "resource_ownership must be an object",
        )
    _validate_ownership_inventory(profile, manifest, ownership)
    _validate_owner_values(ownership, catalog)


def _validate_ownership_inventory(profile: dict[str, Any], manifest: dict[str, Any], ownership: dict[str, str]) -> None:
    expected = resource_ids(profile, manifest)
    missing = expected - set(ownership)
    extra = set(ownership) - expected
    if missing:
        raise StudioContractError(
            400,
            "resource_ownership",
            f"missing resource ownership: {sorted(missing)[0]}",
        )
    if extra:
        raise StudioContractError(
            400,
            "resource_ownership",
            f"unknown resource ownership: {sorted(extra)[0]}",
        )



def _validate_owner_values(ownership: dict[str, str], catalog: list[dict[str, Any]]) -> None:
    catalog_by_id = {feature["id"]: feature for feature in catalog}
    allowed_owners = {"core", "custom", *catalog_by_id}
    invalid_owners = sorted(
        resource
        for resource, owner in ownership.items()
        if not isinstance(owner, str) or owner not in allowed_owners
    )
    if invalid_owners:
        resource = invalid_owners[0]
        raise StudioContractError(
            400,
            f"resource_ownership.{resource}",
            "owner must be core, custom, or a catalog feature ID",
        )


def _validate_feature_state(feature_state: Any, catalog_by_id: dict[str, dict[str, Any]]) -> None:
    catalog_ids = set(catalog_by_id)
    if not isinstance(feature_state, dict) or set(feature_state) != catalog_ids:
        raise StudioContractError(
            400,
            "feature_state",
            "feature_state must define every catalog feature exactly",
        )
    _validate_feature_shapes(feature_state, catalog_by_id)


def _validate_feature_shapes(feature_state: dict[str, dict[str, Any]], catalog_by_id: dict[str, dict[str, Any]]) -> None:
    for feature_id in sorted(catalog_by_id):
        _validate_feature_shape(feature_id, feature_state[feature_id], catalog_by_id[feature_id])


def _validate_feature_shape(feature_id: str, state: Any, feature: dict[str, Any]) -> None:
    if not isinstance(state, dict) or set(state) != {"enabled", "settings"}:
        raise StudioContractError(400, f"feature_state.{feature_id}", "feature state requires boolean enabled and object settings")
    if state.get("enabled").__class__ is not bool or not isinstance(state.get("settings"), dict):
        raise StudioContractError(400, f"feature_state.{feature_id}", "feature state requires boolean enabled and object settings")
    if feature["locked"] and not state["enabled"]:
        raise StudioContractError(422, f"feature_state.{feature_id}.enabled", "locked features must remain enabled")
    _validate_safe(state["settings"], f"feature_state.{feature_id}.settings")


def _validate_feature_dependencies(ownership: dict[str, str], feature_state: dict[str, dict[str, Any]], catalog_by_id: dict[str, dict[str, Any]]) -> None:
    _validate_enabled_dependencies(feature_state, catalog_by_id)
    _validate_resource_owner_features(ownership, feature_state, catalog_by_id)


def _validate_enabled_dependencies(feature_state: dict[str, dict[str, Any]], catalog_by_id: dict[str, dict[str, Any]]) -> None:
    for feature_id in sorted(catalog_by_id):
        if not feature_state[feature_id]["enabled"]:
            continue
        disabled_dependencies = sorted(
            dependency
            for dependency in catalog_by_id[feature_id]["dependencies"]
            if not feature_state[dependency]["enabled"]
        )
        if disabled_dependencies:
            raise StudioContractError(
                422,
                f"feature_state.{feature_id}.enabled",
                "enabled feature requires enabled dependency: "
                f"{disabled_dependencies[0]}",
            )


def _validate_resource_owner_features(ownership: dict[str, str], feature_state: dict[str, dict[str, Any]], catalog_by_id: dict[str, dict[str, Any]]) -> None:
    for resource in sorted(ownership):
        owner = ownership[resource]
        if owner in catalog_by_id and not feature_state[owner]["enabled"]:
            raise StudioContractError(
                422,
                f"resource_ownership.{resource}",
                f"resource owner feature must be enabled: {owner}",
            )
