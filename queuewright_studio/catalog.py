"""Studio catalog validation and default ownership classification."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable


CORE_OWNER = "core"
CUSTOM_OWNER = "custom"


def load_catalog(catalog_path: Path, unsafe_setting: Callable[[Any, str], object]) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    features = catalog.get("features") if isinstance(catalog, dict) else None
    if not isinstance(features, list):
        raise RuntimeError("Studio catalog must contain a features list")
    feature_ids = [feature.get("id") for feature in features]
    if not _valid_features(features, feature_ids):
        raise RuntimeError("Studio catalog features are invalid")
    _validate_dependencies(features, set(feature_ids), unsafe_setting)
    return catalog


def _valid_features(features: list[Any], feature_ids: list[Any]) -> bool:
    return (
        all(isinstance(feature_id, str) for feature_id in feature_ids)
        and len(feature_ids) == len(set(feature_ids))
        and all(
            feature.get("default_enabled").__class__ is bool
            and feature.get("locked").__class__ is bool
            and isinstance(feature.get("settings"), dict)
            for feature in features
        )
    )


def _validate_dependencies(
    features: list[dict[str, Any]],
    feature_ids: set[str],
    unsafe_setting: Callable[[Any, str], object],
) -> None:
    dependencies_by_id: dict[str, set[str]] = {}
    for feature in features:
        if unsafe_setting(feature["settings"], "catalog.settings") is not None:
            raise RuntimeError("Studio catalog feature settings are unsafe")
        dependencies = feature.get("dependencies")
        if not _valid_dependency_list(dependencies):
            raise RuntimeError(f"Studio catalog feature {feature['id']} dependencies are invalid")
        unknown = set(dependencies) - feature_ids
        if unknown:
            raise RuntimeError(
                f"Studio catalog feature {feature['id']} has unknown dependency: {sorted(unknown)[0]}"
            )
        dependencies_by_id[feature["id"]] = set(dependencies)
    _validate_acyclic(dependencies_by_id)


def _valid_dependency_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and len(value) == len(set(value))
    )


def _validate_acyclic(dependencies_by_id: dict[str, set[str]]) -> None:
    remaining = copy.deepcopy(dependencies_by_id)
    complete: set[str] = set()
    while remaining:
        ready = sorted(key for key, dependencies in remaining.items() if dependencies <= complete)
        if not ready:
            raise RuntimeError(
                "Studio catalog feature dependencies contain a cycle: "
                f"{sorted(remaining)[0]}"
            )
        for feature_id in ready:
            complete.add(feature_id)
            del remaining[feature_id]


def default_resource_ownership(
    profile: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, str]:
    ownership: dict[str, str] = {}
    add = _ownership_adder(ownership)
    _add_identity_ownership(manifest, add)
    handoff_tags, uat_tags, sensitive_tags = _ownership_tag_sets(profile, manifest)
    _add_tag_ownership(profile, manifest, handoff_tags, uat_tags, sensitive_tags, add)
    _add_catalog_resource_ownership(manifest, handoff_tags, sensitive_tags, add)
    _add_object_manager_ownership(manifest, add)
    _add_scenario_ownership(profile, add)
    return dict(sorted(ownership.items()))


def _ownership_adder(ownership: dict[str, str]) -> Callable[[str, str, str], None]:
    def add(collection: str, key: str, owner: str) -> None:
        ownership[f"{collection}:{key}"] = owner

    return add


def _add_identity_ownership(manifest: dict[str, Any], add: Callable[[str, str, str], None]) -> None:
    for group in manifest["groups"]:
        add(
            "groups",
            group["key"],
            "sensitive_area_handling" if group.get("restricted") is True else CORE_OWNER,
        )
    for collection in ("organizations", "roles"):
        for resource in manifest[collection]:
            add(collection, resource["key"], CORE_OWNER)
    for collection in ("agents", "customers"):
        for user in manifest["users"][collection]:
            add(collection, user["key"], "dummy_users_uat")


def _ownership_tag_sets(
    profile: dict[str, Any], manifest: dict[str, Any]
) -> tuple[set[str], set[str], set[str]]:
    profile_uat = profile["uat"]
    handoff = profile_uat.get("handoff_probe", {})
    handoff_tags = {handoff.get("pending_tag"), handoff.get("recorded_tag")} - {None}
    uat_tags = {
        tag
        for scenario in profile_uat["scenarios"]
        for tag in scenario.get("expected_tags", [])
    }
    sensitive_tags = _sensitive_tags(manifest)
    return handoff_tags, uat_tags, sensitive_tags


def _sensitive_tags(manifest: dict[str, Any]) -> set[str]:
    sensitive_trigger_tags = {
        tag
        for trigger in manifest["triggers"]
        if _named_for(trigger, "sensitive")
        or "group in S" in trigger.get("conditions", {}).get("all", [])
        for tag in _action_tags(trigger)
    }
    return {tag for tag in manifest["tags"] if _is_sensitive_tag(tag, sensitive_trigger_tags)}


def _is_sensitive_tag(tag: str, trigger_tags: set[str]) -> bool:
    lowered = tag.lower()
    return tag in trigger_tags or "sensitive" in lowered or "restricted" in lowered


def enabled_features(
    features: list[dict[str, Any]], ownership: dict[str, str]
) -> set[str]:
    resource_owners = set(ownership.values())
    enabled = {
        feature["id"]
        for feature in features
        if feature["locked"] or feature["id"] in resource_owners
    }
    dependencies_by_id = {
        feature["id"]: set(feature["dependencies"])
        for feature in features
    }
    while True:
        required = _required_dependencies(enabled, dependencies_by_id)
        expanded = enabled | required
        if expanded == enabled:
            return enabled
        enabled = expanded


def _required_dependencies(
    enabled: set[str], dependencies_by_id: dict[str, set[str]]
) -> set[str]:
    required: set[str] = set()
    for feature_id in enabled:
        required.update(dependencies_by_id[feature_id])
    return required


def _action_tags(resource: dict[str, Any]) -> set[str]:
    return {
        action.partition(":")[2]
        for action in resource.get("actions", [])
        if isinstance(action, str) and action.startswith("add_tag:")
    }


def _named_for(resource: dict[str, Any], marker: str) -> bool:
    return any(marker in str(resource.get(field, "")).lower() for field in ("key", "name"))


def _add_tag_ownership(
    profile: dict[str, Any],
    manifest: dict[str, Any],
    handoff_tags: set[str],
    uat_tags: set[str],
    sensitive_tags: set[str],
    add: Callable[[str, str, str], None],
) -> None:
    job_marker = profile["uat"].get("job_probe", {}).get("marker_tag")
    for tag in manifest["tags"]:
        owner = CUSTOM_OWNER
        if tag in handoff_tags:
            owner = "cross_department_handoff"
        elif tag == job_marker:
            owner = "scheduled_reviews"
        elif tag in sensitive_tags:
            owner = "sensitive_area_handling"
        elif tag in uat_tags:
            owner = "access_matrix"
        add("tags", tag, owner)


def _add_catalog_resource_ownership(
    manifest: dict[str, Any],
    handoff_tags: set[str],
    sensitive_tags: set[str],
    add: Callable[[str, str, str], None],
) -> None:
    collection_owners = {
        "overviews": "overviews",
        "checklist_templates": "checklists",
        "jobs": "scheduled_reviews",
        "report_profiles": "report_profiles",
    }
    for collection, owner in collection_owners.items():
        for resource in manifest[collection]:
            add(collection, resource["key"], owner)
    for collection, default_owner in (("macros", "macros"), ("triggers", "triggers")):
        for resource in manifest[collection]:
            add(collection, resource["key"], _automation_owner(resource, default_owner, handoff_tags, sensitive_tags))


def _automation_owner(
    resource: dict[str, Any],
    default_owner: str,
    handoff_tags: set[str],
    sensitive_tags: set[str],
) -> str:
    tags = _action_tags(resource)
    if tags & handoff_tags or _named_for(resource, "handoff"):
        return "cross_department_handoff"
    if (
        tags & sensitive_tags
        or _named_for(resource, "sensitive")
        or "group in S" in resource.get("conditions", {}).get("all", [])
    ):
        return "sensitive_area_handling"
    return default_owner


def _add_object_manager_ownership(
    manifest: dict[str, Any], add: Callable[[str, str, str], None]
) -> None:
    field_owners = {
        "ticket_fields": "ticket_fields",
        "user_fields": "user_classification",
        "organization_fields": "organization_classification",
        "group_fields": "group_classification",
    }
    object_manager = manifest["object_manager"]
    for collection, owner in field_owners.items():
        for field in object_manager[collection]:
            field_name = field["name"].lower()
            field_owner = "cross_department_handoff" if "handoff" in field_name else owner
            if "sensitive" in field_name:
                field_owner = "sensitive_area_handling"
            add("object_manager_fields", field["name"], field_owner)
    for workflow in object_manager["core_workflows"]:
        add("core_workflows", workflow["key"], CORE_OWNER)


def _add_scenario_ownership(
    profile: dict[str, Any], add: Callable[[str, str, str], None]
) -> None:
    profile_uat = profile["uat"]
    handoff = profile_uat.get("handoff_probe", {})
    job_probe = profile_uat.get("job_probe", {})
    for scenario in profile_uat["scenarios"]:
        owner = "access_matrix"
        if scenario["key"] == handoff.get("ticket_key") or scenario.get("kind") == "transfer":
            owner = "cross_department_handoff"
        elif scenario["key"] == job_probe.get("ticket_key"):
            owner = "scheduled_reviews"
        add("uat_scenarios", scenario["key"], owner)
