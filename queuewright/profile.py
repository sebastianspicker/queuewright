"""Strict, local-only JSON profile loading and validation."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, NoReturn

from .errors import ConfigurationError


RESOURCE_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
PROFILE_KEY = re.compile(r"^[a-z][a-z0-9_-]*$")
MANIFEST_KEY = re.compile(r"^[a-z][a-z0-9_-]*-v[0-9]+$")
NAMESPACE = re.compile(r"^[a-z][a-z0-9_]*_$")
FORBIDDEN_ACTIONS = {
    "ai",
    "close",
    "delete",
    "group_move",
    "mail",
    "owner_change",
    "public_article",
    "webhook",
}
ALLOWED_MACRO_ACTIONS = {
    "add_tag",
    "clear_owner",
    "internal_note",
    "set_group",
    "set_owner_current_user",
    "set_state_closed",
    "set_state_open",
    "set_state_pending_customer",
    "set_state_pending_internal",
}
ALLOWED_AUTOMATION_ACTIONS = {"add_tag", "internal_note"}
ARGUMENT_ACTIONS = {"add_tag", "internal_note", "set_group"}
ALLOWED_ROLE_ACL = {
    "change",
    "create",
    "full",
    "overview",
    "read",
    "read_change_overview",
}
FIELD_COLLECTIONS = (
    "ticket_fields",
    "user_fields",
    "organization_fields",
    "group_fields",
)
SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1.1"}
PROFILE_FIELDS = {
    "display_name",
    "identity",
    "manifest",
    "offline_only",
    "presentation",
    "profile_key",
    "schema_version",
    "uat",
}
MANIFEST_FIELDS = {
    "checklist_templates",
    "groups",
    "jobs",
    "macros",
    "managed_prefix",
    "manifest_key",
    "object_manager",
    "organizations",
    "overviews",
    "reference_sets",
    "report_profiles",
    "roles",
    "safety_contract",
    "schema_version",
    "tags",
    "technical_namespace",
    "triggers",
    "uat",
    "users",
}
SAFETY_REQUIRED_FIELDS = {
    "activation_strategy",
    "allow_delete",
    "allow_existing_object_writes",
    "production_group_reference",
}
SAFETY_ALLOWED_FIELDS = SAFETY_REQUIRED_FIELDS | {
    "global_surfaces_accepted",
    "identity_resolution",
    "object_manager",
    "production_impact_claim",
}
GROUP_FIELDS = {
    "active",
    "key",
    "kind",
    "name",
    "parent",
    "restricted",
    "service_code",
}
ORGANIZATION_FIELDS = {
    "active",
    "class",
    "domain_assignment",
    "key",
    "name",
    "shared",
}
ROLE_FIELDS = {"acl", "key", "name"}
OVERVIEW_FIELDS = {"conditions", "key", "name", "roles"}
OVERVIEW_CONDITION_FIELDS = {"group", "organization", "owner", "state", "tag"}
MACRO_FIELDS = {"actions", "key", "name", "scope"}
CHECKLIST_FIELDS = {"active", "items", "key", "name"}
TRIGGER_FIELDS = {
    "actions",
    "active",
    "conditions",
    "external_effects",
    "idempotency",
    "key",
    "name",
}
JOB_FIELDS = {
    "actions",
    "active",
    "conditions",
    "external_effects",
    "forbidden_actions",
    "idempotency",
    "key",
    "name",
    "schedule",
    "schedule_note",
}
REPORT_FIELDS = {"active", "conditions", "key", "name"}
OBJECT_MANAGER_FIELDS = {
    "activation",
    "core_workflows",
    "group_fields",
    "implementation_sequence",
    "organization_fields",
    "production_impact_claim",
    "restart_required",
    "tenant_default",
    "ticket_fields",
    "user_fields",
}
OBJECT_FIELD_FIELDS = {
    "api_only",
    "name",
    "options",
    "required_by_workflow",
    "type",
}
WORKFLOW_FIELDS = {"actions", "context", "key", "match"}
MANIFEST_UAT_FIELDS = {
    "article_visibility",
    "outbound_communication",
    "retention",
    "ticket_count",
    "title_prefix",
}
PROFILE_UAT_FIELDS = {
    "access_matrix",
    "article_visibility",
    "defaults",
    "handoff_probe",
    "job_probe",
    "outbound_communication",
    "retention",
    "scenarios",
    "title_prefix",
}
SCENARIO_BASE_FIELDS = {
    "agent",
    "correlation_template",
    "customer",
    "expected_tags",
    "group",
    "key",
    "kind",
    "label",
    "number",
    "synthetic_attachment",
}
HANDOFF_PROBE_FIELDS = {
    "agent",
    "expected_owner",
    "pending_tag",
    "recorded_tag",
    "source_group",
    "target_group",
    "ticket_key",
}
JOB_PROBE_FIELDS = {
    "agent",
    "expected_internal_notes",
    "final_schedule",
    "job_key",
    "marker_tag",
    "subject",
    "ticket_key",
}
IDENTITY_FIELDS = {
    "agent_firstname",
    "agent_login_template",
    "customer_firstname",
    "customer_login_template",
    "dummy_only",
    "email_template",
    "notifications",
}
PRESENTATION_FIELDS = {
    "core_workflow_names",
    "field_labels",
    "object_manager_positions",
    "option_labels",
}
SENSITIVE_FILENAMES = {
    ".env",
    "credentials.json",
    "secrets.json",
    "token",
    "token_full",
}
SENSITIVE_SUFFIXES = (".key", ".p12", ".pem", ".pfx", ".secrets.json")


def _fail(message: str) -> NoReturn:
    raise ConfigurationError(message)


def _canonical_hash(value: Any) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _shape(
    value: Any,
    label: str,
    *,
    required: set[str],
    allowed: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    allowed_fields = required if allowed is None else allowed
    missing = required - set(value)
    unknown = set(value) - allowed_fields
    if missing:
        _fail(f"{label} misses required field: {sorted(missing)[0]}")
    if unknown:
        _fail(f"{label} has unsupported field: {sorted(unknown)[0]}")
    return value


def _reject_url_values(value: Any, label: str = "configuration") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_url_values(child, f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_url_values(child, f"{label}[{index}]")
    elif isinstance(value, str) and re.search(r"\b(?:https?|wss?)://", value, re.I):
        _fail(f"{label} must not contain a URL")


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"cannot read JSON {path}: {error}")
    if not isinstance(value, dict):
        _fail(f"JSON object required: {path}")
    return value


def _repo_root(path: Path) -> Path | None:
    for ancestor in (path, *path.parents):
        if (ancestor / ".git").exists():
            return ancestor
    return None


def _sensitive_path(path: Path) -> bool:
    for part in path.parts:
        lowered = part.lower()
        if (
            lowered == ".local"
            or lowered in SENSITIVE_FILENAMES
            or lowered.startswith(".env.")
            or lowered.endswith(SENSITIVE_SUFFIXES)
        ):
            return True
    return False


def is_forbidden_local_path(path: str | Path) -> bool:
    """Return whether a path crosses the package's no-secret/no-run-data fence."""
    return _sensitive_path(Path(path).resolve())


def _keyed_items(items: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        _fail(f"{label} must be a list")
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("key"), str)
            or RESOURCE_KEY.fullmatch(item["key"]) is None
        ):
            _fail(f"{label} entries require a valid key")
        if item["key"] in result:
            _fail(f"duplicate {label} key: {item['key']}")
        result[item["key"]] = item
    return result


def _managed_names(
    items: dict[str, dict[str, Any]], label: str, prefix: str
) -> None:
    for key, item in items.items():
        name = item.get("name")
        if not isinstance(name, str) or not name.startswith(prefix):
            _fail(f"{label} {key} name must start with managed_prefix")


def _references(values: Any, valid: set[str], label: str) -> list[str]:
    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        _fail(f"{label} must be a list of keys")
    if len(values) != len(set(values)):
        _fail(f"{label} contains duplicate keys")
    unknown = set(values) - valid
    if unknown:
        _fail(f"{label} references unknown key: {sorted(unknown)[0]}")
    return values


def _action_parts(action: str, label: str) -> tuple[str, str | None]:
    parts = action.split(":", 1)
    verb = parts[0].strip().lower()
    argument = parts[1].strip() if len(parts) == 2 else None
    if not verb or (len(parts) == 2 and not argument):
        _fail(f"{label} has a malformed action")
    if verb in ARGUMENT_ACTIONS and argument is None:
        _fail(f"{label} action {verb} requires an argument")
    if verb not in ARGUMENT_ACTIONS and argument is not None:
        _fail(f"{label} action {verb} does not accept an argument")
    canonical = verb if argument is None else f"{verb}:{argument}"
    if action != canonical:
        _fail(f"{label} action must use canonical spelling: {canonical}")
    return verb, argument


def _validate_identity(
    identity: Any, users: dict[str, Any], profile_key: str
) -> None:
    if not isinstance(identity, dict) or set(identity) != IDENTITY_FIELDS:
        _fail("identity must contain exactly the required offline identity fields")
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
    for field in ("agent_firstname", "customer_firstname"):
        if not isinstance(identity[field], str) or not identity[field].strip():
            _fail("identity first names must be non-empty")
    if identity["dummy_only"] is not True or identity["notifications"] is not False:
        _fail("identity must be dummy-only with notifications disabled")


def _validate_groups(
    raw_groups: Any, prefix: str, schema_version: str
) -> tuple[dict[str, dict[str, Any]], set[str], set[str]]:
    groups = _keyed_items(raw_groups, "groups")
    if not groups:
        _fail("at least one managed group is required")
    _managed_names(groups, "group", prefix)
    leaf_keys = {
        key for key, group in groups.items() if group.get("kind") == "leaf"
    }
    restricted = {
        key for key, group in groups.items() if group.get("restricted") is True
    }
    parent_by_key: dict[str, str] = {}
    root_keys: list[str] = []
    service_codes: set[str] = set()
    for key, group in groups.items():
        kind = group.get("kind")
        base_fields = {"active", "key", "kind", "name"}
        container_fields = (
            base_fields
            if schema_version == "1.0"
            else base_fields | {"parent"}
        )
        _shape(
            group,
            f"group {key}",
            required=(
                base_fields
                if kind == "container"
                else base_fields | {"parent", "service_code"}
            ),
            allowed=(container_fields if kind == "container" else GROUP_FIELDS),
        )
        if kind not in {"container", "leaf"} or group.get("active") is not True:
            _fail(f"group {key} must be an active container or leaf")
        if kind == "container":
            parent = group.get("parent")
            if schema_version == "1.0":
                if parent is not None or group.get("restricted") is True:
                    _fail(
                        f"container group {key} cannot have a parent or restriction"
                    )
            elif parent is None:
                root_keys.append(key)
            elif not isinstance(parent, str) or not parent:
                _fail(f"container group parent invalid: {key}")
            else:
                parent_by_key[key] = parent
            continue
        if "restricted" in group and type(group["restricted"]) is not bool:
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

    if schema_version == "1.0":
        for key in leaf_keys:
            parent = parent_by_key[key]
            if parent not in groups or groups[parent].get("kind") != "container":
                _fail(f"leaf group parent invalid: {key}")
        return groups, leaf_keys, restricted

    if len(root_keys) != 1:
        _fail("schema 1.1 groups require exactly one root container")
    for key, parent in parent_by_key.items():
        if parent not in groups or groups[parent].get("kind") != "container":
            _fail(f"group parent invalid: {key}")

    root_key = root_keys[0]
    for key in groups:
        cursor = key
        seen: set[str] = set()
        while cursor in parent_by_key:
            if cursor in seen:
                _fail(f"group hierarchy contains a cycle at: {cursor}")
            seen.add(cursor)
            cursor = parent_by_key[cursor]
        if cursor != root_key:
            _fail(f"group is unreachable from root {root_key}: {key}")
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
    for key, agent in agents.items():
        _shape(agent, f"agent {key}", required={"key", "role"})
        if agent.get("role") not in roles:
            _fail(f"agent {key} references unknown role")
    for key, customer in customers.items():
        _shape(
            customer,
            f"customer {key}",
            required={"key", "organization"},
        )
        if customer.get("organization") not in organizations:
            _fail(f"customer {key} references unknown organization")

    agent_constraints = users["agent_constraints"]
    role_only_keys = (
        [
            key
            for key, value in agent_constraints.items()
            if key.endswith("_role_only") and value is True
        ]
        if isinstance(agent_constraints, dict)
        else []
    )
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


def _validate_macros(
    macros: dict[str, dict[str, Any]],
    prefix: str,
    leaf_keys: set[str],
    tags: set[str],
) -> None:
    _managed_names(macros, "macro", prefix)
    for key, macro in macros.items():
        _shape(macro, f"macro {key}", required=MACRO_FIELDS)
        actions = macro.get("actions")
        if macro.get("scope") != "H" or not isinstance(actions, list) or not actions:
            _fail(f"macro {key} must have H scope and actions")
        for action in actions:
            if not isinstance(action, str):
                _fail(f"macro {key} actions must be strings")
            verb, argument = _action_parts(action, f"macro {key}")
            if verb not in ALLOWED_MACRO_ACTIONS:
                _fail(f"macro {key} has unsupported action: {verb}")
            if verb == "add_tag" and argument not in tags:
                _fail(f"macro {key} references an undeclared tag")
            if verb == "set_group" and argument not in leaf_keys:
                _fail(f"macro {key} references an unknown group")


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


def _validate_automation(
    items: dict[str, dict[str, Any]],
    label: str,
    prefix: str,
    tags: set[str],
) -> None:
    _managed_names(items, label, prefix)
    for key, item in items.items():
        if label == "trigger":
            _shape(
                item,
                f"trigger {key}",
                required={
                    "actions",
                    "active",
                    "conditions",
                    "external_effects",
                    "key",
                    "name",
                },
                allowed=TRIGGER_FIELDS,
            )
        else:
            _shape(
                item,
                f"job {key}",
                required={
                    "actions",
                    "active",
                    "conditions",
                    "forbidden_actions",
                    "key",
                    "name",
                    "schedule",
                },
                allowed=JOB_FIELDS,
            )
        condition_map = item.get("conditions")
        condition_map = _shape(
            condition_map,
            f"{label} {key} conditions",
            required={"all"},
        )
        conditions = condition_map["all"]
        if not isinstance(conditions, list) or not all(
            isinstance(value, str) for value in conditions
        ):
            _fail(f"{label} {key} conditions must be a string list")
        has_group = any(
            condition in {"group in H", "group in S"}
            for condition in conditions
        )
        has_organization = "organization in O" in conditions
        if not has_group or not has_organization:
            _fail(f"{label} {key} lacks required H/S and O fence")
        if label == "trigger" and item.get("external_effects") is not False:
            _fail(f"trigger {key} must explicitly disable external effects")
        if label == "job" and item.get("external_effects", False) is not False:
            _fail(f"job {key} has external effects")
        actions = item.get("actions")
        if not isinstance(actions, list) or not actions or not all(
            isinstance(action, str) for action in actions
        ):
            _fail(f"{label} {key} actions must be a non-empty string list")
        for action in actions:
            verb, argument = _action_parts(action, f"{label} {key}")
            if verb not in ALLOWED_AUTOMATION_ACTIONS:
                _fail(f"{label} {key} has unsupported action: {verb}")
            if verb == "add_tag" and argument not in tags:
                _fail(f"{label} {key} adds an undeclared tag")
        if item.get("active") is not True:
            _fail(f"{label} {key} must declare its desired active state")
        for optional_text in ("idempotency", "schedule_note"):
            if optional_text in item and (
                not isinstance(item[optional_text], str)
                or not item[optional_text].strip()
            ):
                _fail(f"{label} {key} {optional_text} must be non-empty text")
        if label == "job":
            forbidden = item.get("forbidden_actions")
            if (
                not isinstance(forbidden, list)
                or not all(isinstance(value, str) for value in forbidden)
                or not FORBIDDEN_ACTIONS.issubset(set(forbidden))
                or not isinstance(item.get("schedule"), str)
                or not item["schedule"]
            ):
                _fail(f"job {key} must declare schedule and all forbidden actions")


def _validate_reports(
    reports: dict[str, dict[str, Any]], prefix: str
) -> None:
    _managed_names(reports, "report profile", prefix)
    for key, report in reports.items():
        _shape(report, f"report profile {key}", required=REPORT_FIELDS)
        conditions = _shape(
            report.get("conditions"),
            f"report profile {key} conditions",
            required={"group", "organization"},
        )
        if (
            report.get("active") is not True
            or conditions.get("group") not in {"H", "S"}
            or conditions.get("organization") != "O"
        ):
            _fail(f"report profile {key} must be active and H/S plus O fenced")


def _validate_object_manager(
    object_manager: Any,
    presentation: Any,
    namespace: str,
    prefix: str,
) -> dict[str, set[str]]:
    required = {
        "core_workflows",
        "group_fields",
        "organization_fields",
        "tenant_default",
        "ticket_fields",
        "user_fields",
    }
    object_manager = _shape(
        object_manager,
        "object_manager",
        required=required,
        allowed=OBJECT_MANAGER_FIELDS,
    )
    for text_field in ("activation", "production_impact_claim"):
        if text_field in object_manager and (
            not isinstance(object_manager[text_field], str)
            or not object_manager[text_field].strip()
        ):
            _fail(f"object_manager.{text_field} must be non-empty text")
    if "restart_required" in object_manager and type(
        object_manager["restart_required"]
    ) is not bool:
        _fail("object_manager.restart_required must be boolean")
    if "implementation_sequence" in object_manager and (
        not isinstance(object_manager["implementation_sequence"], list)
        or not all(
            isinstance(value, str) and value.strip()
            for value in object_manager["implementation_sequence"]
        )
    ):
        _fail("object_manager.implementation_sequence must be a string list")

    field_names: set[str] = set()
    option_values: set[str] = set()
    ticket_options: dict[str, set[str]] = {}
    for collection in FIELD_COLLECTIONS:
        fields = object_manager[collection]
        if not isinstance(fields, list):
            _fail(f"object_manager.{collection} must be a list")
        for field in fields:
            _shape(
                field,
                f"object_manager.{collection} field",
                required={"name", "options", "type"},
                allowed=OBJECT_FIELD_FIELDS,
            )
            if (
                not isinstance(field.get("name"), str)
                or not field["name"].startswith(namespace)
                or field.get("type") not in {"select", "tree_select"}
            ):
                _fail(f"object_manager.{collection} has an invalid field")
            name = field["name"]
            if name in field_names:
                _fail(f"duplicate object manager field: {name}")
            field_names.add(name)
            options = field.get("options")
            if (
                not isinstance(options, list)
                or not options
                or not all(isinstance(option, str) and option for option in options)
                or len(options) != len(set(options))
            ):
                _fail(f"object manager options must be unique strings: {name}")
            option_values.update(options)
            for boolean_field in ("api_only", "required_by_workflow"):
                if boolean_field in field and type(field[boolean_field]) is not bool:
                    _fail(f"object manager {boolean_field} must be boolean: {name}")
            if collection == "ticket_fields":
                logical_name = name.removeprefix(namespace)
                if not logical_name or logical_name in ticket_options:
                    _fail(f"duplicate logical ticket field name: {name}")
                ticket_options[logical_name] = set(options)

    tenant_default = _shape(
        object_manager["tenant_default"],
        "object_manager.tenant_default",
        required={"default", "hidden", "optional"},
        allowed={"default", "hidden", "no_date_or_datetime", "optional"},
    )
    if (
        tenant_default.get("hidden") is not True
        or tenant_default.get("optional") is not True
        or tenant_default.get("default", object()) is not None
        or tenant_default.get("no_date_or_datetime", True) is not True
    ):
        _fail("tenant defaults must be hidden, optional, null, and date-free")

    workflows = _keyed_items(object_manager["core_workflows"], "core workflows")
    for key, workflow in workflows.items():
        _shape(workflow, f"core workflow {key}", required=WORKFLOW_FIELDS)
        if (
            workflow.get("context")
            not in {"agent_create", "agent_edit", "customer_create"}
            or not isinstance(workflow.get("match"), str)
            or not workflow["match"]
            or not isinstance(workflow.get("actions"), str)
            or not workflow["actions"]
        ):
            _fail(f"core workflow {key} has an invalid declarative contract")

    if not isinstance(presentation, dict) or set(presentation) != PRESENTATION_FIELDS:
        _fail("presentation must contain exactly the required fields")
    for name in ("field_labels", "option_labels", "core_workflow_names"):
        mapping = presentation[name]
        if not isinstance(mapping, dict) or not all(
            isinstance(key, str) and isinstance(value, str) and value.strip()
            for key, value in mapping.items()
        ):
            _fail(f"presentation {name} must be a non-empty-string map")
    if set(presentation["field_labels"]) != field_names:
        _fail("field labels must cover object manager fields exactly")
    if set(presentation["option_labels"]) != option_values:
        _fail("option labels must cover object manager options exactly")
    if set(presentation["core_workflow_names"]) != set(workflows):
        _fail("workflow names must cover core workflows exactly")
    if any(
        not name.startswith(prefix)
        for name in presentation["core_workflow_names"].values()
    ):
        _fail("core workflow names must start with managed_prefix")

    positions = presentation["object_manager_positions"]
    if (
        not isinstance(positions, dict)
        or set(positions) != {"Group", "Organization", "Ticket", "User"}
    ):
        _fail("object manager positions must cover Ticket/User/Organization/Group")
    for object_name, position in positions.items():
        if (
            not isinstance(position, dict)
            or set(position) != {"start", "step"}
            or not all(
                type(position[key]) is int and position[key] > 0
                for key in ("start", "step")
            )
        ):
            _fail(f"object manager position for {object_name} is invalid")
    return ticket_options


def _validate_uat(
    profile_uat: Any,
    manifest_uat: Any,
    leaf_keys: set[str],
    agents: dict[str, dict[str, Any]],
    customers: dict[str, dict[str, Any]],
    tags: set[str],
    jobs: dict[str, dict[str, Any]],
    ticket_options: dict[str, set[str]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    profile_uat = _shape(
        profile_uat,
        "profile UAT",
        required={
            "access_matrix",
            "article_visibility",
            "defaults",
            "outbound_communication",
            "retention",
            "scenarios",
            "title_prefix",
        },
        allowed=PROFILE_UAT_FIELDS,
    )
    manifest_uat = _shape(
        manifest_uat,
        "manifest UAT",
        required=MANIFEST_UAT_FIELDS,
    )
    for uat, label in ((profile_uat, "profile"), (manifest_uat, "manifest")):
        if (
            uat.get("article_visibility") != "internal"
            or uat.get("retention") != "close_and_retain"
            or uat.get("outbound_communication") is not False
        ):
            _fail(f"invalid {label} UAT safety contract")
    if not isinstance(profile_uat.get("title_prefix"), str) or not profile_uat[
        "title_prefix"
    ]:
        _fail("profile UAT requires a title_prefix")
    if manifest_uat.get("title_prefix") != profile_uat["title_prefix"]:
        _fail("profile and manifest UAT title_prefix must match")
    defaults = _shape(
        profile_uat.get("defaults"),
        "UAT defaults",
        required=set(),
        allowed=set(ticket_options),
    )
    for field, value in defaults.items():
        if value is not None and (
            not isinstance(value, str) or value not in ticket_options[field]
        ):
            _fail(f"UAT default for {field} is not a declared field option")

    scenarios = _keyed_items(profile_uat.get("scenarios"), "UAT scenarios")
    if manifest_uat.get("ticket_count") != len(scenarios):
        _fail("UAT ticket_count must equal scenario count")
    numbers = [scenario.get("number") for scenario in scenarios.values()]
    if (
        any(type(value) is not int or value < 1 for value in numbers)
        or len(numbers) != len(set(numbers))
    ):
        _fail("UAT scenario numbers must be positive and unique")
    for key, scenario in scenarios.items():
        _shape(
            scenario,
            f"UAT scenario {key}",
            required={
                "agent",
                "customer",
                "expected_tags",
                "group",
                "key",
                "kind",
                "label",
                "number",
            },
            allowed=SCENARIO_BASE_FIELDS | set(ticket_options),
        )
        if (
            not isinstance(scenario.get("kind"), str)
            or not scenario["kind"]
            or not isinstance(scenario.get("label"), str)
            or not scenario["label"]
            or scenario.get("group") not in leaf_keys
            or scenario.get("customer") not in customers
            or scenario.get("agent") not in agents
        ):
            _fail(f"invalid UAT scenario: {key}")
        expected_tags = scenario.get("expected_tags")
        if (
            not isinstance(expected_tags, list)
            or not expected_tags
            or not all(isinstance(tag, str) for tag in expected_tags)
            or len(expected_tags) != len(set(expected_tags))
            or not set(expected_tags).issubset(tags)
        ):
            _fail(f"invalid UAT scenario tags: {key}")
        correlation = scenario.get("correlation_template")
        if correlation is not None and (
            not isinstance(correlation, str) or correlation.count("{run}") != 1
        ):
            _fail(f"invalid UAT correlation template: {key}")
        if "synthetic_attachment" in scenario and type(
            scenario["synthetic_attachment"]
        ) is not bool:
            _fail(f"invalid UAT attachment flag: {key}")
        for field, options in ticket_options.items():
            if field in scenario and (
                not isinstance(scenario[field], str)
                or scenario[field] not in options
            ):
                _fail(f"invalid UAT option override {field}: {key}")

    access_matrix = _shape(
        profile_uat.get("access_matrix"),
        "UAT access_matrix",
        required={"seed_keys"},
    )
    seed_keys = access_matrix["seed_keys"]
    if (
        not isinstance(seed_keys, list)
        or not seed_keys
        or not all(isinstance(key, str) for key in seed_keys)
        or len(seed_keys) != len(set(seed_keys))
        or not set(seed_keys).issubset(scenarios)
        or any(scenarios[key].get("kind") != "seed" for key in seed_keys)
    ):
        _fail("UAT seed coverage invalid")

    handoff = profile_uat.get("handoff_probe")
    if handoff is not None:
        _shape(handoff, "handoff_probe", required=HANDOFF_PROBE_FIELDS)
        if (
            handoff.get("ticket_key") not in scenarios
            or handoff.get("agent") not in agents
            or handoff.get("source_group") not in leaf_keys
            or handoff.get("target_group") not in leaf_keys
            or handoff.get("pending_tag") not in tags
            or handoff.get("recorded_tag") not in tags
            or handoff.get("expected_owner") != "unassigned"
        ):
            _fail("invalid handoff_probe contract")

    job_probe = profile_uat.get("job_probe")
    if job_probe is not None:
        _shape(job_probe, "job_probe", required=JOB_PROBE_FIELDS)
        if (
            job_probe.get("ticket_key") not in scenarios
            or job_probe.get("agent") not in agents
            or job_probe.get("job_key") not in jobs
            or job_probe.get("marker_tag") not in tags
            or not isinstance(job_probe.get("subject"), str)
            or not job_probe["subject"]
            or type(job_probe.get("expected_internal_notes")) is not int
            or job_probe["expected_internal_notes"] < 1
            or not isinstance(job_probe.get("final_schedule"), str)
            or not job_probe["final_schedule"]
        ):
            _fail("invalid job_probe contract")
    return scenarios, seed_keys


def load_profile(profile: str | Path) -> dict[str, Any]:
    """Load only an explicit local profile and its local JSON manifest."""
    supplied = Path(profile)
    profile_path = (
        supplied / "profile.json" if supplied.is_dir() else supplied
    ).resolve()
    if profile_path.suffix.lower() != ".json" or _sensitive_path(profile_path):
        _fail("profile path must be a non-sensitive JSON file")
    bundle = _json(profile_path)
    manifest_name = bundle.get("manifest")
    if (
        not isinstance(manifest_name, str)
        or not manifest_name
        or Path(manifest_name).is_absolute()
        or Path(manifest_name).suffix.lower() != ".json"
    ):
        _fail("profile manifest must be a non-empty relative JSON path")
    manifest_path = (profile_path.parent / manifest_name).resolve()
    if manifest_path == profile_path or _sensitive_path(manifest_path):
        _fail("manifest path is forbidden")
    allowed_root = (_repo_root(profile_path.parent) or profile_path.parent).resolve()
    try:
        manifest_path.relative_to(allowed_root)
    except ValueError:
        _fail("manifest path escapes its allowed root")
    return {
        "profile": bundle,
        "manifest": _json(manifest_path),
        "profile_path": profile_path,
        "manifest_path": manifest_path,
    }


def validate_loaded_profile(loaded: dict[str, Any]) -> dict[str, Any]:
    """Validate one already-loaded profile/manifest snapshot."""
    bundle = loaded["profile"]
    manifest = loaded["manifest"]
    if set(bundle) != PROFILE_FIELDS:
        _fail("profile must contain exactly the supported fields")
    if set(manifest) != MANIFEST_FIELDS:
        _fail("manifest must contain exactly the supported fields")
    _reject_url_values(bundle, "profile")
    _reject_url_values(manifest, "manifest")
    schema_version = bundle.get("schema_version")
    if (
        schema_version not in SUPPORTED_SCHEMA_VERSIONS
        or manifest.get("schema_version") != schema_version
    ):
        _fail("profile and manifest schema_version must match 1.0 or 1.1")
    if (
        not isinstance(bundle.get("profile_key"), str)
        or PROFILE_KEY.fullmatch(bundle["profile_key"]) is None
    ):
        _fail("invalid profile_key")
    if (
        not isinstance(manifest.get("manifest_key"), str)
        or MANIFEST_KEY.fullmatch(manifest["manifest_key"]) is None
    ):
        _fail("invalid manifest_key")
    if (
        not isinstance(bundle.get("display_name"), str)
        or not bundle["display_name"].strip()
        or bundle.get("offline_only") is not True
    ):
        _fail("profile requires display_name and offline_only true")

    prefix = manifest.get("managed_prefix")
    namespace = manifest.get("technical_namespace")
    if (
        not isinstance(prefix, str)
        or len(prefix) < 2
        or not isinstance(namespace, str)
        or NAMESPACE.fullmatch(namespace) is None
    ):
        _fail("invalid managed prefix or technical namespace")
    safety = _shape(
        manifest.get("safety_contract"),
        "safety_contract",
        required=SAFETY_REQUIRED_FIELDS,
        allowed=SAFETY_ALLOWED_FIELDS,
    )
    if (
        safety.get("allow_existing_object_writes") is not False
        or safety.get("allow_delete") is not False
        or safety.get("production_group_reference") != "forbidden"
        or safety.get("activation_strategy")
        != "create_inactive_then_readback_collision_scan_then_activate"
    ):
        _fail("invalid safety contract")
    surfaces = safety.get("global_surfaces_accepted")
    if surfaces is not None and (
        not isinstance(surfaces, list)
        or not all(isinstance(value, str) and value.strip() for value in surfaces)
    ):
        _fail("safety_contract.global_surfaces_accepted must be a string list")
    for text_field in (
        "identity_resolution",
        "object_manager",
        "production_impact_claim",
    ):
        if text_field in safety and (
            not isinstance(safety[text_field], str)
            or not safety[text_field].strip()
        ):
            _fail(f"safety_contract.{text_field} must be non-empty text")

    groups, leaf_keys, restricted = _validate_groups(
        manifest.get("groups"), prefix, schema_version
    )
    reference_sets = manifest.get("reference_sets")
    if (
        not isinstance(reference_sets, dict)
        or set(reference_sets) != {"H", "O", "R", "S"}
        or reference_sets.get("H")
        != "all managed ticket-bearing group keys"
        or reference_sets.get("O") != "all managed organization keys"
        or reference_sets.get("R") != "all managed role keys"
        or not isinstance(reference_sets["S"], list)
        or not all(
            isinstance(value, str) and RESOURCE_KEY.fullmatch(value) is not None
            for value in reference_sets["S"]
        )
        or set(reference_sets["S"]) != restricted
        or len(reference_sets["S"]) != len(set(reference_sets["S"]))
    ):
        _fail("reference set descriptors are invalid or S does not match restricted leaves")

    organizations = _validate_organizations(manifest.get("organizations"), prefix)
    roles = _validate_roles(manifest.get("roles"), prefix, leaf_keys)
    users = manifest.get("users")
    agents, customers = _validate_users(users, roles, organizations)
    _validate_identity(bundle.get("identity"), users, bundle["profile_key"])

    overviews = _keyed_items(manifest.get("overviews"), "overviews")
    macros = _keyed_items(manifest.get("macros"), "macros")
    checklists = _keyed_items(
        manifest.get("checklist_templates"), "checklist templates"
    )
    triggers = _keyed_items(manifest.get("triggers"), "triggers")
    jobs = _keyed_items(manifest.get("jobs"), "jobs")
    reports = _keyed_items(manifest.get("report_profiles"), "report profiles")
    tags = manifest.get("tags")
    if (
        not isinstance(tags, list)
        or not tags
        or not all(
            isinstance(tag, str) and tag.startswith(namespace.removesuffix("_") + "/")
            for tag in tags
        )
        or len(tags) != len(set(tags))
    ):
        _fail("tags must be unique and namespaced")
    tag_set = set(tags)

    _validate_overviews(overviews, prefix)
    _validate_macros(macros, prefix, leaf_keys, tag_set)
    _validate_checklists(checklists, prefix)
    _validate_automation(triggers, "trigger", prefix, tag_set)
    _validate_automation(jobs, "job", prefix, tag_set)
    _validate_reports(reports, prefix)
    ticket_options = _validate_object_manager(
        manifest.get("object_manager"),
        bundle.get("presentation"),
        namespace,
        prefix,
    )
    scenarios, seed_keys = _validate_uat(
        bundle.get("uat"),
        manifest.get("uat"),
        leaf_keys,
        agents,
        customers,
        tag_set,
        jobs,
        ticket_options,
    )

    object_manager = manifest["object_manager"]
    field_count = sum(len(object_manager[name]) for name in FIELD_COLLECTIONS)
    counts = {
        "access_matrix_checks": len(agents) * len(seed_keys),
        "agents": len(agents),
        "checklist_templates": len(checklists),
        "containers": len(groups) - len(leaf_keys),
        "core_workflows": len(object_manager["core_workflows"]),
        "customers": len(customers),
        "groups": len(groups),
        "jobs": len(jobs),
        "leaf_groups": len(leaf_keys),
        "macros": len(macros),
        "object_manager_fields": field_count,
        "organizations": len(organizations),
        "overviews": len(overviews),
        "report_profiles": len(reports),
        "roles": len(roles),
        "tags": len(tags),
        "triggers": len(triggers),
        "uat_scenarios": len(scenarios),
    }
    return {
        "counts": counts,
        "display_name": bundle["display_name"],
        "manifest_key": manifest["manifest_key"],
        "profile_hash": _canonical_hash(bundle),
        "profile_key": bundle["profile_key"],
        "source_hash": _canonical_hash(manifest),
    }


def validate_profile(profile: str | Path) -> dict[str, Any]:
    """Load and fail closed on one local configuration snapshot."""
    return validate_loaded_profile(load_profile(profile))
