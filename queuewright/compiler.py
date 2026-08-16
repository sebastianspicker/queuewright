"""Deterministic compilation of validated profiles into inert symbolic plans."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .errors import ConfigurationError
from .manifest_inventory import manifest_inventory
from .profile import FIELD_COLLECTIONS, load_profile, validate_loaded_profile


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _operation(
    resource: str,
    key: str,
    desired_state: Any,
    depends_on: list[str] | None = None,
    *,
    supports_inactive: bool = True,
) -> dict[str, Any]:
    """Describe intent without pretending that a profile spec is an API payload."""
    return {
        "action": "create_inactive" if supports_inactive else "ensure_present",
        "depends_on": sorted(set(depends_on or [])),
        "desired_state": copy.deepcopy(desired_state),
        "id": f"{resource}:{key}",
        "initial_state": {"active": False} if supports_inactive else {},
        "key": key,
        "resource": resource,
    }


def _operations_by_id(operations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for operation in operations:
        if operation["id"] in by_id:
            raise ConfigurationError(f"duplicate symbolic operation: {operation['id']}")
        by_id[operation["id"]] = operation
    return by_id


def _validate_dependencies(operations: list[dict[str, Any]], known: set[str]) -> None:
    for operation in operations:
        unknown = set(operation["depends_on"]) - known
        if unknown:
            raise ConfigurationError(
                f"symbolic operation {operation['id']} has unknown dependency: "
                f"{min(unknown)}"
            )


def _topological_order(by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = dict(by_id)
    complete: set[str] = set()
    ordered: list[dict[str, Any]] = []
    while remaining:
        ready = [
            operation
            for operation in remaining.values()
            if set(operation["depends_on"]).issubset(complete)
        ]
        if not ready:
            raise ConfigurationError("symbolic plan contains a dependency cycle")
        for operation in sorted(ready, key=lambda value: value["id"]):
            ordered.append(operation)
            complete.add(operation["id"])
            del remaining[operation["id"]]
    for sequence, operation in enumerate(ordered, start=1):
        operation["sequence"] = sequence
    return ordered


def _dependency_order(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a stable topological order and reject unknown or cyclic inputs."""
    by_id = _operations_by_id(operations)
    _validate_dependencies(operations, set(by_id))
    return _topological_order(by_id)


def _keys(items: list[dict[str, Any]]) -> list[str]:
    return sorted(item["key"] for item in items)


def _append_operations(
    operations: list[dict[str, Any]],
    collection: str,
    items: list[dict[str, Any]],
    dependencies: list[str],
) -> None:
    for item in items:
        operations.append(_operation(collection, item["key"], item, dependencies))


def _field_operations(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    operations: list[dict[str, Any]] = []
    field_ids: list[str] = []
    for collection in FIELD_COLLECTIONS:
        for field in manifest["object_manager"][collection]:
            operation = _operation("object_manager_fields", field["name"], field)
            operations.append(operation)
            field_ids.append(operation["id"])
    return operations, field_ids


def _base_operations(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    operations: list[dict[str, Any]] = []
    for group in manifest["groups"]:
        dependencies = [f"groups:{group['parent']}"] if group.get("parent") else []
        operations.append(_operation("groups", group["key"], group, dependencies))
    _append_operations(operations, "organizations", manifest["organizations"], [])
    for role in manifest["roles"]:
        dependencies = [f"groups:{key}" for values in role["acl"].values() for key in values]
        operations.append(_operation("roles", role["key"], role, dependencies))
    for tag in manifest["tags"]:
        operations.append(_operation("tags", tag, {"name": tag}, supports_inactive=False))
    fields, field_ids = _field_operations(manifest)
    operations.extend(fields)
    return operations, field_ids


def _append_automation_operations(
    operations: list[dict[str, Any]], manifest: dict[str, Any], dependencies: list[str]
) -> None:
    for collection in ("triggers", "jobs"):
        _append_operations(operations, collection, manifest[collection], dependencies)


def _append_dependent_operations(
    operations: list[dict[str, Any]], manifest: dict[str, Any], field_ids: list[str]
) -> None:

    group_ids = [f"groups:{group['key']}" for group in manifest["groups"] if group["kind"] == "leaf"]
    organization_ids = [f"organizations:{item['key']}" for item in manifest["organizations"]]
    role_ids = [f"roles:{item['key']}" for item in manifest["roles"]]
    tag_ids = [f"tags:{tag}" for tag in manifest["tags"]]
    _append_operations(operations, "core_workflows", manifest["object_manager"]["core_workflows"], field_ids + group_ids + role_ids)
    for agent in manifest["users"]["agents"]:
        operations.append(_operation("agents", agent["key"], agent, [f"roles:{agent['role']}"]))
    for customer in manifest["users"]["customers"]:
        operations.append(_operation("customers", customer["key"], customer, [f"organizations:{customer['organization']}"]))
    _append_operations(operations, "overviews", manifest["overviews"], group_ids + organization_ids + role_ids)
    _append_operations(operations, "macros", manifest["macros"], group_ids + tag_ids)
    _append_operations(operations, "checklist_templates", manifest["checklist_templates"], [])
    _append_automation_operations(operations, manifest, group_ids + organization_ids + tag_ids)
    _append_operations(operations, "report_profiles", manifest["report_profiles"], group_ids + organization_ids)


def _build_operations(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    operations, field_ids = _base_operations(manifest)
    _append_dependent_operations(operations, manifest, field_ids)
    return operations


def _inventory(bundle: dict[str, Any], manifest: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "agents": _keys(manifest["users"]["agents"]),
        "customers": _keys(manifest["users"]["customers"]),
        "uat_scenarios": _keys(bundle["uat"]["scenarios"]),
        **manifest_inventory(manifest),
    }


def compile_loaded_profile(loaded: dict[str, Any]) -> dict[str, Any]:
    """Compile one validated in-memory snapshot into a symbolic plan."""
    summary = validate_loaded_profile(loaded)
    bundle = loaded["profile"]
    manifest = loaded["manifest"]
    operations = _dependency_order(_build_operations(manifest))
    inventory = _inventory(bundle, manifest)
    plan = {
        "counts": {**summary["counts"], "operations": len(operations)},
        "identity": bundle["identity"],
        "inventory": inventory,
        "manifest_key": summary["manifest_key"],
        "operations": operations,
        "presentation": bundle["presentation"],
        "profile_key": summary["profile_key"],
        "reference_sets": {
            "H": inventory["leaf_groups"],
            "O": inventory["organizations"],
            "R": inventory["roles"],
            "S": sorted(manifest["reference_sets"]["S"]),
        },
        "safety": {
            "allow_delete": False,
            "allow_existing_object_writes": False,
            "execution": "symbolic_plan_only",
            "network_capability": False,
            "offline_only": True,
        },
        "schema_version": "1.0",
        "source_hashes": {
            "manifest": summary["source_hash"],
            "profile": summary["profile_hash"],
        },
        "uat": bundle["uat"],
    }
    if bundle["schema_version"] != "1.0":
        plan["source_schema_version"] = bundle["schema_version"]
    plan["plan_hash"] = hashlib.sha256(
        _canonical(plan).encode("utf-8")
    ).hexdigest()
    return plan


def compile_plan(profile: str | Path) -> dict[str, Any]:
    """Load once and compile a deterministic, non-executable local plan."""
    return compile_loaded_profile(load_profile(profile))
