"""Complexity budgets for symbolic planning and project derivation."""

from __future__ import annotations

from typing import Any

from ..configuration import FIELD_COLLECTIONS
from ..contracts.json import canonical_json
from ..errors import ConfigurationError

MAX_COMPILED_OPERATIONS = 10_000
MAX_PLAN_DEPENDENCIES = 100_000
MAX_PLAN_DEPENDENCY_ID_BYTES = 8 * 1024 * 1024
MAX_DERIVED_SERVICE_CHECKS = 1_000_000
MAX_DERIVED_SERVICE_BYTES = 8 * 1024 * 1024


def _identifier_bytes(prefix: str, values: list[str]) -> int:
    return sum(len(f"{prefix}{value}".encode()) for value in values)


def _json_bytes(value: Any) -> int:
    return len(canonical_json(value).encode())


def validate_compilation_budget(loaded: dict[str, Any]) -> None:
    """Reject validated bundles whose compiled form would exceed fixed budgets.

    The calculations mirror the compiler's dependency fan-out without building
    the repeated dependency lists.  Callers must validate the bundle shape and
    references before invoking this function.
    """
    profile = loaded["profile"]
    manifest = loaded["manifest"]
    object_manager = manifest["object_manager"]

    groups = manifest["groups"]
    organizations = manifest["organizations"]
    roles = manifest["roles"]
    tags = manifest["tags"]
    agents = manifest["users"]["agents"]
    customers = manifest["users"]["customers"]
    workflows = object_manager["core_workflows"]
    overviews = manifest["overviews"]
    macros = manifest["macros"]
    checklists = manifest["checklist_templates"]
    triggers = manifest["triggers"]
    jobs = manifest["jobs"]
    reports = manifest["report_profiles"]
    fields = [
        field
        for collection in FIELD_COLLECTIONS
        for field in object_manager[collection]
    ]

    operation_count = sum(
        len(collection)
        for collection in (
            groups,
            organizations,
            roles,
            tags,
            fields,
            workflows,
            agents,
            customers,
            overviews,
            macros,
            checklists,
            triggers,
            jobs,
            reports,
        )
    )
    if operation_count > MAX_COMPILED_OPERATIONS:
        raise ConfigurationError(
            "symbolic plan exceeds the maximum of "
            f"{MAX_COMPILED_OPERATIONS} operations"
        )

    leaf_keys = [group["key"] for group in groups if group["kind"] == "leaf"]
    organization_keys = [item["key"] for item in organizations]
    role_keys = [item["key"] for item in roles]
    field_keys = [item["name"] for item in fields]

    role_group_keys = [
        {key for values in role["acl"].values() for key in values}
        for role in roles
    ]
    role_group_keys_by_role = dict(zip(role_keys, role_group_keys, strict=True))
    base_dependencies = sum(1 for group in groups if group.get("parent"))
    base_dependencies += sum(len(keys) for keys in role_group_keys)
    base_dependencies += len(agents) + len(customers)

    workflow_width = len(fields) + len(leaf_keys) + len(roles)
    overview_width = len(leaf_keys) + len(organizations) + len(roles)
    macro_width = len(leaf_keys) + len(tags)
    automation_width = len(leaf_keys) + len(organizations) + len(tags)
    report_width = len(leaf_keys) + len(organizations)
    dependency_count = (
        base_dependencies
        + len(workflows) * workflow_width
        + len(overviews) * overview_width
        + len(macros) * macro_width
        + (len(triggers) + len(jobs)) * automation_width
        + len(reports) * report_width
    )
    if dependency_count > MAX_PLAN_DEPENDENCIES:
        raise ConfigurationError(
            "symbolic plan exceeds the maximum of "
            f"{MAX_PLAN_DEPENDENCIES} dependencies"
        )

    leaf_bytes = _identifier_bytes("groups:", leaf_keys)
    organization_bytes = _identifier_bytes("organizations:", organization_keys)
    role_bytes = _identifier_bytes("roles:", role_keys)
    tag_bytes = _identifier_bytes("tags:", tags)
    field_bytes = _identifier_bytes("object_manager_fields:", field_keys)
    dependency_id_bytes = sum(
        len(f"groups:{group['parent']}".encode())
        for group in groups
        if group.get("parent")
    )
    dependency_id_bytes += sum(
        _identifier_bytes("groups:", list(keys)) for keys in role_group_keys
    )
    dependency_id_bytes += sum(
        len(f"roles:{agent['role']}".encode()) for agent in agents
    )
    dependency_id_bytes += sum(
        len(f"organizations:{customer['organization']}".encode())
        for customer in customers
    )
    dependency_id_bytes += len(workflows) * (
        field_bytes + leaf_bytes + role_bytes
    )
    dependency_id_bytes += len(overviews) * (
        leaf_bytes + organization_bytes + role_bytes
    )
    dependency_id_bytes += len(macros) * (leaf_bytes + tag_bytes)
    dependency_id_bytes += (len(triggers) + len(jobs)) * (
        leaf_bytes + organization_bytes + tag_bytes
    )
    dependency_id_bytes += len(reports) * (leaf_bytes + organization_bytes)
    if dependency_id_bytes > MAX_PLAN_DEPENDENCY_ID_BYTES:
        raise ConfigurationError(
            "symbolic plan dependency identifiers exceed the maximum of "
            f"{MAX_PLAN_DEPENDENCY_ID_BYTES} bytes"
        )

    role_by_key = {role["key"]: role for role in roles}
    role_acl_entries = sum(
        len(values) for role in roles for values in role["acl"].values()
    )
    agent_acl_entries = sum(
        len(values)
        for agent in agents
        for values in role_by_key[agent["role"]]["acl"].values()
    )
    role_acl_collections = sum(len(role["acl"]) for role in roles)
    agent_acl_collections = sum(
        len(role_by_key[agent["role"]]["acl"]) for agent in agents
    )
    scenario_count = len(profile["uat"]["scenarios"])
    derived_service_checks = len(workflows) + len(groups) * (
        role_acl_collections
        + role_acl_entries
        + agent_acl_collections
        + agent_acl_entries
        + scenario_count
    )
    if derived_service_checks > MAX_DERIVED_SERVICE_CHECKS:
        raise ConfigurationError(
            "project service derivation exceeds the maximum of "
            f"{MAX_DERIVED_SERVICE_CHECKS} membership checks"
        )

    # Include structural overhead as well as every input string copied into the
    # service projection.  Agent identifiers are multiplied by the number of
    # groups reachable through their role, which is the dominant fan-out.
    derived_service_bytes = len(groups) * 256
    derived_service_bytes += sum(
        sum(
            _json_bytes(group.get(field))
            for field in ("key", "name", "kind", "parent", "service_code")
        )
        for group in groups
    )
    for role, accessible_groups in zip(roles, role_group_keys, strict=True):
        largest_permission = max(
            (_json_bytes(permission) for permission in role["acl"]), default=0
        )
        derived_service_bytes += len(accessible_groups) * (
            48 + _json_bytes(role["key"]) + largest_permission
        )
    derived_service_bytes += sum(
        len(role_group_keys_by_role[agent["role"]])
        * (1 + _json_bytes(agent["key"]))
        for agent in agents
    )
    derived_service_bytes += sum(
        1 + _json_bytes(scenario["key"])
        for scenario in profile["uat"]["scenarios"]
    )
    if derived_service_bytes > MAX_DERIVED_SERVICE_BYTES:
        raise ConfigurationError(
            "project service projection exceeds the maximum of "
            f"{MAX_DERIVED_SERVICE_BYTES} serialized bytes"
        )
