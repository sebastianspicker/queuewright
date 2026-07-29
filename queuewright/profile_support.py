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
    _validate_action_parts(verb, argument, len(parts), label)
    canonical = verb if argument is None else f"{verb}:{argument}"
    if action != canonical:
        _fail(f"{label} action must use canonical spelling: {canonical}")
    return verb, argument


def _validate_action_parts(verb: str, argument: str | None, part_count: int, label: str) -> None:
    if not verb or (part_count == 2 and not argument):
        _fail(f"{label} has a malformed action")
    if verb in ARGUMENT_ACTIONS and argument is None:
        _fail(f"{label} action {verb} requires an argument")
    if verb not in ARGUMENT_ACTIONS and argument is not None:
        _fail(f"{label} action {verb} does not accept an argument")
