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


def _validate_safe(value: Any, path: str) -> None:
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is float:
        if value == value and value not in (float("inf"), -float("inf")):
            return
        raise StudioContractError(400, path, "settings must contain finite JSON numbers")
    if isinstance(value, str):
        if "://" in value:
            raise StudioContractError(400, path, "settings must not contain URLs")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_safe(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise StudioContractError(400, path, "settings object keys must be strings")
            parts = _key_parts(key)
            if (
                parts & SENSITIVE_SETTING_NAMES
                or {"api", "key"} <= parts
                or {"private", "key"} <= parts
            ):
                raise StudioContractError(400, f"{path}.{key}", "sensitive setting names are forbidden")
            _validate_safe(item, f"{path}.{key}")
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
    if not isinstance(ownership, dict):
        raise StudioContractError(
            400,
            "resource_ownership",
            "resource_ownership must be an object",
        )
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

    catalog_ids = set(catalog_by_id)
    if not isinstance(feature_state, dict) or set(feature_state) != catalog_ids:
        raise StudioContractError(
            400,
            "feature_state",
            "feature_state must define every catalog feature exactly",
        )
    for feature_id in sorted(catalog_ids):
        state = feature_state[feature_id]
        if (
            not isinstance(state, dict)
            or set(state) != {"enabled", "settings"}
            or type(state.get("enabled")) is not bool
            or not isinstance(state.get("settings"), dict)
        ):
            raise StudioContractError(
                400,
                f"feature_state.{feature_id}",
                "feature state requires boolean enabled and object settings",
            )
        if catalog_by_id[feature_id]["locked"] and not state["enabled"]:
            raise StudioContractError(
                422,
                f"feature_state.{feature_id}.enabled",
                "locked features must remain enabled",
            )
        _validate_safe(state["settings"], f"feature_state.{feature_id}.settings")

    for feature_id in sorted(catalog_ids):
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

    for resource in sorted(ownership):
        owner = ownership[resource]
        if owner in catalog_by_id and not feature_state[owner]["enabled"]:
            raise StudioContractError(
                422,
                f"resource_ownership.{resource}",
                f"resource owner feature must be enabled: {owner}",
            )
    return copy.deepcopy(ownership), copy.deepcopy(feature_state)
