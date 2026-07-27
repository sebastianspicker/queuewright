"""Deterministic compilation of validated profiles into inert symbolic plans."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .errors import ConfigurationError
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


def _dependency_order(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a stable topological order and reject unknown or cyclic inputs."""
    by_id: dict[str, dict[str, Any]] = {}
    for operation in operations:
        if operation["id"] in by_id:
            raise ConfigurationError(f"duplicate symbolic operation: {operation['id']}")
        by_id[operation["id"]] = operation
    known = set(by_id)
    for operation in operations:
        unknown = set(operation["depends_on"]) - known
        if unknown:
            raise ConfigurationError(
                f"symbolic operation {operation['id']} has unknown dependency: "
                f"{sorted(unknown)[0]}"
            )

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


def _keys(items: list[dict[str, Any]]) -> list[str]:
    return sorted(item["key"] for item in items)


def compile_loaded_profile(loaded: dict[str, Any]) -> dict[str, Any]:
    """Compile one validated in-memory snapshot into a symbolic plan."""
    summary = validate_loaded_profile(loaded)
    bundle = loaded["profile"]
    manifest = loaded["manifest"]
    operations: list[dict[str, Any]] = []

    for group in manifest["groups"]:
        dependencies = (
            [f"groups:{group['parent']}"] if group.get("parent") else []
        )
        operations.append(
            _operation("groups", group["key"], group, dependencies)
        )
    for organization in manifest["organizations"]:
        operations.append(
            _operation("organizations", organization["key"], organization)
        )
    for role in manifest["roles"]:
        dependencies = [
            f"groups:{group_key}"
            for group_keys in role["acl"].values()
            for group_key in group_keys
        ]
        operations.append(
            _operation("roles", role["key"], role, dependencies)
        )
    for tag in manifest["tags"]:
        operations.append(
            _operation(
                "tags",
                tag,
                {"name": tag},
                supports_inactive=False,
            )
        )

    object_field_ids: list[str] = []
    for collection in FIELD_COLLECTIONS:
        for field in manifest["object_manager"][collection]:
            operation = _operation(
                "object_manager_fields",
                field["name"],
                field,
            )
            operations.append(operation)
            object_field_ids.append(operation["id"])

    group_ids = [
        f"groups:{group['key']}"
        for group in manifest["groups"]
        if group["kind"] == "leaf"
    ]
    organization_ids = [
        f"organizations:{organization['key']}"
        for organization in manifest["organizations"]
    ]
    role_ids = [f"roles:{role['key']}" for role in manifest["roles"]]
    tag_ids = [f"tags:{tag}" for tag in manifest["tags"]]

    for workflow in manifest["object_manager"]["core_workflows"]:
        operations.append(
            _operation(
                "core_workflows",
                workflow["key"],
                workflow,
                object_field_ids + group_ids + role_ids,
            )
        )
    for agent in manifest["users"]["agents"]:
        operations.append(
            _operation(
                "agents",
                agent["key"],
                agent,
                [f"roles:{agent['role']}"],
            )
        )
    for customer in manifest["users"]["customers"]:
        operations.append(
            _operation(
                "customers",
                customer["key"],
                customer,
                [f"organizations:{customer['organization']}"],
            )
        )
    for overview in manifest["overviews"]:
        operations.append(
            _operation(
                "overviews",
                overview["key"],
                overview,
                group_ids + organization_ids + role_ids,
            )
        )
    for macro in manifest["macros"]:
        operations.append(
            _operation(
                "macros",
                macro["key"],
                macro,
                group_ids + tag_ids,
            )
        )
    for checklist in manifest["checklist_templates"]:
        operations.append(
            _operation("checklist_templates", checklist["key"], checklist)
        )
    for collection in ("triggers", "jobs"):
        for automation in manifest[collection]:
            operations.append(
                _operation(
                    collection,
                    automation["key"],
                    automation,
                    group_ids + organization_ids + tag_ids,
                )
            )
    for report in manifest["report_profiles"]:
        operations.append(
            _operation(
                "report_profiles",
                report["key"],
                report,
                group_ids + organization_ids,
            )
        )

    operations = _dependency_order(operations)
    object_manager_fields = sorted(
        field["name"]
        for collection in FIELD_COLLECTIONS
        for field in manifest["object_manager"][collection]
    )
    inventory = {
        "agents": _keys(manifest["users"]["agents"]),
        "checklist_templates": _keys(manifest["checklist_templates"]),
        "containers": sorted(
            group["key"]
            for group in manifest["groups"]
            if group["kind"] == "container"
        ),
        "core_workflows": _keys(
            manifest["object_manager"]["core_workflows"]
        ),
        "customers": _keys(manifest["users"]["customers"]),
        "groups": _keys(manifest["groups"]),
        "jobs": _keys(manifest["jobs"]),
        "leaf_groups": sorted(
            group["key"]
            for group in manifest["groups"]
            if group["kind"] == "leaf"
        ),
        "macros": _keys(manifest["macros"]),
        "object_manager_fields": object_manager_fields,
        "organizations": _keys(manifest["organizations"]),
        "overviews": _keys(manifest["overviews"]),
        "report_profiles": _keys(manifest["report_profiles"]),
        "roles": _keys(manifest["roles"]),
        "tags": sorted(manifest["tags"]),
        "triggers": _keys(manifest["triggers"]),
        "uat_scenarios": _keys(bundle["uat"]["scenarios"]),
    }
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
