"""Resource inventory, default ownership classification, and enabled-feature closure."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any, NamedTuple

from ..configuration import FIELD_COLLECTIONS

CORE_OWNER = "core"
CUSTOM_OWNER = "custom"
FIXED_OWNERS = {
    "organizations": CORE_OWNER,
    "roles": CORE_OWNER,
    "agents": "dummy_users_uat",
    "customers": "dummy_users_uat",
    "overviews": "overviews",
    "checklist_templates": "checklists",
    "jobs": "scheduled_reviews",
    "report_profiles": "report_profiles",
    "core_workflows": CORE_OWNER,
}
AUTOMATION_OWNERS = {"macros": "macros", "triggers": "triggers"}
FIELD_OWNERS = {
    "ticket_fields": "ticket_fields",
    "user_fields": "user_classification",
    "organization_fields": "organization_classification",
    "group_fields": "group_classification",
}


class _Resource(NamedTuple):
    collection: str
    key: str
    source: str
    item: Any

    @property
    def id(self) -> str:
        return f"{self.collection}:{self.key}"


class _OwnerContext(NamedTuple):
    handoff: dict[str, Any]
    job_probe: dict[str, Any]
    handoff_tags: set[str]
    uat_tags: set[str]
    sensitive_tags: set[str]


def _resources(profile: dict[str, Any], manifest: dict[str, Any]) -> Iterator[_Resource]:
    """Enumerate every resource that Studio ownership covers, in a stable order."""
    for collection in ("groups", "organizations", "roles"):
        for item in manifest[collection]:
            yield _Resource(collection, item["key"], collection, item)
    for collection in ("agents", "customers"):
        for item in manifest["users"][collection]:
            yield _Resource(collection, item["key"], collection, item)
    for tag in manifest["tags"]:
        yield _Resource("tags", tag, "tags", tag)
    for collection in (
        "overviews", "checklist_templates", "jobs", "report_profiles", "macros", "triggers"
    ):
        for item in manifest[collection]:
            yield _Resource(collection, item["key"], collection, item)
    object_manager = manifest["object_manager"]
    for collection in FIELD_COLLECTIONS:
        for field in object_manager[collection]:
            yield _Resource("object_manager_fields", field["name"], collection, field)
    for workflow in object_manager["core_workflows"]:
        yield _Resource("core_workflows", workflow["key"], "core_workflows", workflow)
    for scenario in profile["uat"]["scenarios"]:
        yield _Resource("uat_scenarios", scenario["key"], "uat_scenarios", scenario)


def resource_ids(profile: dict[str, Any], manifest: dict[str, Any]) -> set[str]:
    """Return the exact resource inventory covered by Studio ownership."""
    return {resource.id for resource in _resources(profile, manifest)}


def default_resource_ownership(
    profile: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, str]:
    """Classify every inventoried resource with its default owning feature."""
    context = _owner_context(profile, manifest)
    ownership = {
        resource.id: _owner(resource, context) for resource in _resources(profile, manifest)
    }
    return dict(sorted(ownership.items()))


def _owner_context(profile: dict[str, Any], manifest: dict[str, Any]) -> _OwnerContext:
    profile_uat = profile["uat"]
    handoff = profile_uat.get("handoff_probe", {})
    uat_tags = {
        tag
        for scenario in profile_uat["scenarios"]
        for tag in scenario.get("expected_tags", [])
    }
    return _OwnerContext(
        handoff=handoff,
        job_probe=profile_uat.get("job_probe", {}),
        handoff_tags={handoff.get("pending_tag"), handoff.get("recorded_tag")} - {None},
        uat_tags=uat_tags,
        sensitive_tags=_sensitive_tags(manifest),
    )


def _owner(resource: _Resource, context: _OwnerContext) -> str:
    source = resource.source
    if source in FIXED_OWNERS:
        return FIXED_OWNERS[source]
    if source == "groups":
        return "sensitive_area_handling" if resource.item.get("restricted") is True else CORE_OWNER
    if source == "tags":
        return _tag_owner(resource.item, context)
    if source in AUTOMATION_OWNERS:
        return _automation_owner(resource.item, AUTOMATION_OWNERS[source], context)
    if source in FIELD_OWNERS:
        return _field_owner(resource.item, FIELD_OWNERS[source])
    return _scenario_owner(resource.item, context)


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


def _action_tags(resource: dict[str, Any]) -> set[str]:
    return {
        action.partition(":")[2]
        for action in resource.get("actions", [])
        if isinstance(action, str) and action.startswith("add_tag:")
    }


def _named_for(resource: dict[str, Any], marker: str) -> bool:
    return any(marker in str(resource.get(field, "")).lower() for field in ("key", "name"))


def _tag_owner(tag: str, context: _OwnerContext) -> str:
    if tag in context.handoff_tags:
        return "cross_department_handoff"
    if tag == context.job_probe.get("marker_tag"):
        return "scheduled_reviews"
    if tag in context.sensitive_tags:
        return "sensitive_area_handling"
    if tag in context.uat_tags:
        return "access_matrix"
    return CUSTOM_OWNER


def _automation_owner(
    resource: dict[str, Any], default_owner: str, context: _OwnerContext
) -> str:
    tags = _action_tags(resource)
    if tags & context.handoff_tags or _named_for(resource, "handoff"):
        return "cross_department_handoff"
    if (
        tags & context.sensitive_tags
        or _named_for(resource, "sensitive")
        or "group in S" in resource.get("conditions", {}).get("all", [])
    ):
        return "sensitive_area_handling"
    return default_owner


def _field_owner(field: dict[str, Any], default_owner: str) -> str:
    field_name = field["name"].lower()
    if "sensitive" in field_name:
        return "sensitive_area_handling"
    if "handoff" in field_name:
        return "cross_department_handoff"
    return default_owner


def _scenario_owner(scenario: dict[str, Any], context: _OwnerContext) -> str:
    if scenario["key"] == context.handoff.get("ticket_key") or scenario.get("kind") == "transfer":
        return "cross_department_handoff"
    if scenario["key"] == context.job_probe.get("ticket_key"):
        return "scheduled_reviews"
    return "access_matrix"


def allowed_owners(features: Iterable[dict[str, Any]]) -> set[str]:
    """Return every owner value a resource may name."""
    return {CORE_OWNER, CUSTOM_OWNER, *(feature["id"] for feature in features)}


def dependency_closure(enabled: set[str], features: list[dict[str, Any]]) -> set[str]:
    """Expand enabled feature IDs with every transitive catalog dependency."""
    dependencies_by_id = {feature["id"]: set(feature["dependencies"]) for feature in features}
    while True:
        expanded = enabled | set().union(
            *(dependencies_by_id[feature_id] for feature_id in enabled)
        )
        if expanded == enabled:
            return enabled
        enabled = expanded


def enabled_features(features: list[dict[str, Any]], ownership: dict[str, str]) -> set[str]:
    """Return locked and resource-owning features plus their dependencies."""
    resource_owners = set(ownership.values())
    enabled = {
        feature["id"]
        for feature in features
        if feature["locked"] or feature["id"] in resource_owners
    }
    return dependency_closure(enabled, features)
