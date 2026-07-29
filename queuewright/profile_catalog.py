"""Profile catalog validation."""

from __future__ import annotations

from typing import Any

from .profile_support import (
    ALLOWED_MACRO_ACTIONS,
    ALLOWED_ROLE_ACL,
    CHECKLIST_FIELDS,
    GROUP_FIELDS,
    IDENTITY_FIELDS,
    MACRO_FIELDS,
    ORGANIZATION_FIELDS,
    OVERVIEW_CONDITION_FIELDS,
    OVERVIEW_FIELDS,
    ROLE_FIELDS,
    _action_parts,
    _fail,
    _keyed_items,
    _managed_names,
    _references,
    _shape,
)

def _validate_identity(
    identity: Any, users: dict[str, Any], profile_key: str
) -> None:
    if not isinstance(identity, dict) or set(identity) != IDENTITY_FIELDS:
        _fail("identity must contain exactly the required offline identity fields")
    _validate_identity_login_templates(identity, profile_key)
    _validate_identity_email_template(identity, users, profile_key)
    _validate_identity_names(identity)


def _validate_identity_login_templates(identity: dict[str, Any], profile_key: str) -> None:
    for field in ("agent_login_template", "customer_login_template"):
        if (
            not isinstance(identity[field], str)
            or identity[field].count("{key}") != 1
            or not identity[field].startswith(f"{profile_key}.")
        ):
            _fail(
                f"identity {field} must be profile-namespaced and contain "
                "one {key} placeholder"
            )
    if identity["agent_login_template"] == identity["customer_login_template"]:
        _fail("agent and customer login templates must be distinct")


def _validate_identity_email_template(identity: dict[str, Any], users: dict[str, Any], profile_key: str) -> None:
    email_template = identity["email_template"]
    if (
        not isinstance(email_template, str)
        or email_template.count("{kind}") != 1
        or email_template.count("{key}") != 1
        or not email_template.startswith(f"{profile_key}.")
        or not email_template.endswith("@example.invalid")
        or users.get("email_template") != email_template
    ):
        _fail(
            "identity email_template must match users.email_template, contain "
            "{kind}/{key}, and end in @example.invalid"
        )

def _validate_identity_names(identity: dict[str, Any]) -> None:
    for field in ("agent_firstname", "customer_firstname"):
        if not isinstance(identity[field], str) or not identity[field].strip():
            _fail("identity first names must be non-empty")
    if identity["dummy_only"] is not True or identity["notifications"] is not False:
        _fail("identity must be dummy-only with notifications disabled")


def _validate_schema_11_group_root(root_keys: list[str]) -> str:
    if len(root_keys) != 1:
        _fail("schema 1.1 groups require exactly one root container")
    return root_keys[0]


def _validate_group_parent_references(
    groups: dict[str, dict[str, Any]], parent_by_key: dict[str, str]
) -> None:
    for key, parent in parent_by_key.items():
        if parent not in groups or groups[parent].get("kind") != "container":
            _fail(f"group parent invalid: {key}")


def _group_path_to_root(
    key: str, parent_by_key: dict[str, str], root_key: str
) -> None:
    cursor = key
    seen: set[str] = set()
    while cursor in parent_by_key:
        if cursor in seen:
            _fail(f"group hierarchy contains a cycle at: {cursor}")
        seen.add(cursor)
        cursor = parent_by_key[cursor]
    if cursor != root_key:
        _fail(f"group is unreachable from root {root_key}: {key}")


def _validate_schema_11_group_hierarchy(
    groups: dict[str, dict[str, Any]], parent_by_key: dict[str, str], root_keys: list[str]
) -> None:
    root_key = _validate_schema_11_group_root(root_keys)
    _validate_group_parent_references(groups, parent_by_key)
    for key in groups:
        _group_path_to_root(key, parent_by_key, root_key)


def _validate_container_group(
    key: str,
    group: dict[str, Any],
    schema_version: str,
    root_keys: list[str],
    parent_by_key: dict[str, str],
) -> None:
    parent = group.get("parent")
    if schema_version == "1.0":
        if parent is not None or group.get("restricted") is True:
            _fail(f"container group {key} cannot have a parent or restriction")
    elif parent is None:
        root_keys.append(key)
    elif not isinstance(parent, str) or not parent:
        _fail(f"container group parent invalid: {key}")
    else:
        parent_by_key[key] = parent


def _validate_leaf_group(
    key: str,
    group: dict[str, Any],
    parent_by_key: dict[str, str],
    service_codes: set[str],
) -> None:
    if "restricted" in group and group["restricted"].__class__ is not bool:
        _fail(f"leaf group {key} restricted must be boolean")
    parent = group.get("parent")
    if not isinstance(parent, str) or not parent:
        _fail(f"leaf group parent invalid: {key}")
    parent_by_key[key] = parent
    service_code = group.get("service_code")
    if not isinstance(service_code, str) or not service_code:
        _fail(f"leaf group {key} requires a service_code")
    if service_code in service_codes:
        _fail(f"duplicate leaf service_code: {service_code}")
    service_codes.add(service_code)


def _validate_group_shape(
    key: str,
    group: dict[str, Any],
    schema_version: str,
    root_keys: list[str],
    parent_by_key: dict[str, str],
    service_codes: set[str],
) -> None:
    kind = group.get("kind")
    base_fields = {"active", "key", "kind", "name"}
    container_fields = (
        base_fields if schema_version == "1.0" else base_fields | {"parent"}
    )
    required = (
        base_fields if kind == "container" else base_fields | {"parent", "service_code"}
    )
    allowed = container_fields if kind == "container" else GROUP_FIELDS
    _shape(group, f"group {key}", required=required, allowed=allowed)
    if kind not in {"container", "leaf"} or group.get("active") is not True:
        _fail(f"group {key} must be an active container or leaf")
    if kind == "container":
        _validate_container_group(
            key, group, schema_version, root_keys, parent_by_key
        )
        return
    _validate_leaf_group(key, group, parent_by_key, service_codes)


def _group_key_sets(
    groups: dict[str, dict[str, Any]]
) -> tuple[set[str], set[str]]:
    leaf_keys = {
        key for key, group in groups.items() if group.get("kind") == "leaf"
    }
    restricted = {
        key for key, group in groups.items() if group.get("restricted") is True
    }
    return leaf_keys, restricted


def _validate_legacy_leaf_group_parents(
    groups: dict[str, dict[str, Any]],
    leaf_keys: set[str],
    parent_by_key: dict[str, str],
) -> None:
    for key in leaf_keys:
        parent = parent_by_key[key]
        if parent not in groups or groups[parent].get("kind") != "container":
            _fail(f"leaf group parent invalid: {key}")


def _validate_groups(
    raw_groups: Any, prefix: str, schema_version: str
) -> tuple[dict[str, dict[str, Any]], set[str], set[str]]:
    groups = _keyed_items(raw_groups, "groups")
    if not groups:
        _fail("at least one managed group is required")
    _managed_names(groups, "group", prefix)
    leaf_keys, restricted = _group_key_sets(groups)
    parent_by_key: dict[str, str] = {}
    root_keys: list[str] = []
    service_codes: set[str] = set()
    for key, group in groups.items():
        _validate_group_shape(
            key,
            group,
            schema_version,
            root_keys,
            parent_by_key,
            service_codes,
        )
    if schema_version == "1.0":
        _validate_legacy_leaf_group_parents(groups, leaf_keys, parent_by_key)
        return groups, leaf_keys, restricted
    _validate_schema_11_group_hierarchy(groups, parent_by_key, root_keys)
    return groups, leaf_keys, restricted


def _validate_organizations(
    raw_organizations: Any, prefix: str
) -> dict[str, dict[str, Any]]:
    organizations = _keyed_items(raw_organizations, "organizations")
    if not organizations:
        _fail("at least one managed organization is required")
    _managed_names(organizations, "organization", prefix)
    for key, organization in organizations.items():
        _shape(
            organization,
            f"organization {key}",
            required=ORGANIZATION_FIELDS,
        )
        if (
            organization.get("active") is not True
            or organization.get("shared") is not False
            or organization.get("domain_assignment") is not False
            or not isinstance(organization.get("class"), str)
            or not organization["class"]
        ):
            _fail(
                f"organization {key} must be active, unshared, "
                "non-domain-assigned, and classified"
            )
    return organizations


def _validate_roles(
    raw_roles: Any, prefix: str, leaf_keys: set[str]
) -> dict[str, dict[str, Any]]:
    roles = _keyed_items(raw_roles, "roles")
    if not roles:
        _fail("at least one managed role is required")
    _managed_names(roles, "role", prefix)
    for key, role in roles.items():
        _shape(role, f"role {key}", required=ROLE_FIELDS)
        acl = role.get("acl")
        if not isinstance(acl, dict) or not acl:
            _fail(f"role {key} ACL must be a non-empty object")
        unknown_permissions = set(acl) - ALLOWED_ROLE_ACL
        if unknown_permissions:
            _fail(
                f"role {key} has unsupported ACL permission: "
                f"{sorted(unknown_permissions)[0]}"
            )
        for permission, values in acl.items():
            if not _references(
                values, leaf_keys, f"role {key} ACL {permission}"
            ):
                _fail(f"role {key} ACL {permission} must not be empty")
    return roles


def _validate_agents(
    agents: dict[str, dict[str, Any]], roles: dict[str, dict[str, Any]]
) -> None:
    for key, agent in agents.items():
        _shape(agent, f"agent {key}", required={"key", "role"})
        if agent.get("role") not in roles:
            _fail(f"agent {key} references unknown role")


def _validate_customers(
    customers: dict[str, dict[str, Any]], organizations: dict[str, dict[str, Any]]
) -> None:
    for key, customer in customers.items():
        _shape(customer, f"customer {key}", required={"key", "organization"})
        if customer.get("organization") not in organizations:
            _fail(f"customer {key} references unknown organization")


def _role_only_constraint_keys(agent_constraints: Any) -> list[str]:
    if not isinstance(agent_constraints, dict):
        return []
    return [
        key
        for key, value in agent_constraints.items()
        if key.endswith("_role_only") and value is True
    ]


def _validate_user_constraints(users: dict[str, Any]) -> None:
    agent_constraints = users["agent_constraints"]
    role_only_keys = _role_only_constraint_keys(agent_constraints)
    expected_agent_constraints = {
        "no_admin",
        "no_report_permission",
        "notifications",
        *role_only_keys,
    }
    if (
        not isinstance(agent_constraints, dict)
        or len(role_only_keys) != 1
        or set(agent_constraints) != expected_agent_constraints
        or agent_constraints.get("notifications") is not False
        or agent_constraints.get("no_admin") is not True
        or agent_constraints.get("no_report_permission") is not True
    ):
        _fail("agent constraints must enforce one role, no admin/report, and no notifications")
    if users["customer_constraints"] != {
        "customer_role_only": True,
        "password_login": False,
        "pat": False,
        "saml_identity": False,
    }:
        _fail("customer constraints must disable password, PAT, and SAML identity")


def _validate_users(
    users: Any,
    roles: dict[str, dict[str, Any]],
    organizations: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    required = {
        "agent_constraints",
        "agents",
        "customer_constraints",
        "customers",
        "email_template",
    }
    users = _shape(users, "users", required=required)
    agents = _keyed_items(users["agents"], "agents")
    customers = _keyed_items(users["customers"], "customers")
    if not agents or not customers:
        _fail("at least one dummy agent and customer is required")
    _validate_agents(agents, roles)
    _validate_customers(customers, organizations)
    _validate_user_constraints(users)
    return agents, customers


def _validate_overviews(
    overviews: dict[str, dict[str, Any]], prefix: str
) -> None:
    _managed_names(overviews, "overview", prefix)
    for key, overview in overviews.items():
        _shape(overview, f"overview {key}", required=OVERVIEW_FIELDS)
        conditions = _shape(
            overview.get("conditions"),
            f"overview {key} conditions",
            required={"group", "organization"},
            allowed=OVERVIEW_CONDITION_FIELDS,
        )
        if (
            conditions.get("group") not in {"H", "S"}
            or conditions.get("organization") != "O"
            or overview.get("roles") != "R"
            or not all(isinstance(value, str) and value for value in conditions.values())
        ):
            _fail(f"overview {key} must be fenced by H/S, O, and R")


def _validate_macro_action(
    key: str, action: str, leaf_keys: set[str], tags: set[str]
) -> None:
    verb, argument = _action_parts(action, f"macro {key}")
    if verb not in ALLOWED_MACRO_ACTIONS:
        _fail(f"macro {key} has unsupported action: {verb}")
    if verb == "add_tag" and argument not in tags:
        _fail(f"macro {key} references an undeclared tag")
    if verb == "set_group" and argument not in leaf_keys:
        _fail(f"macro {key} references an unknown group")


def _validate_macro_actions(
    key: str, macro: dict[str, Any], leaf_keys: set[str], tags: set[str]
) -> None:
    actions = macro.get("actions")
    if macro.get("scope") != "H" or not isinstance(actions, list) or not actions:
        _fail(f"macro {key} must have H scope and actions")
    for action in actions:
        if not isinstance(action, str):
            _fail(f"macro {key} actions must be strings")
        _validate_macro_action(key, action, leaf_keys, tags)


def _validate_macros(
    macros: dict[str, dict[str, Any]],
    prefix: str,
    leaf_keys: set[str],
    tags: set[str],
) -> None:
    _managed_names(macros, "macro", prefix)
    for key, macro in macros.items():
        _shape(macro, f"macro {key}", required=MACRO_FIELDS)
        _validate_macro_actions(key, macro, leaf_keys, tags)


def _validate_checklists(
    checklists: dict[str, dict[str, Any]], prefix: str
) -> None:
    _managed_names(checklists, "checklist", prefix)
    for key, checklist in checklists.items():
        _shape(checklist, f"checklist {key}", required=CHECKLIST_FIELDS)
        items = checklist.get("items")
        if (
            checklist.get("active") is not False
            or not isinstance(items, list)
            or not items
            or not all(isinstance(item, str) and item.strip() for item in items)
        ):
            _fail(f"checklist {key} must remain inactive with non-empty items")
