"""Object manager field, core workflow, and presentation validation."""

from __future__ import annotations

from typing import Any, NamedTuple

from .rules import FIELD_COLLECTIONS, _fail, _keyed_items, _shape

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
PRESENTATION_FIELDS = {
    "core_workflow_names",
    "field_labels",
    "object_manager_positions",
    "option_labels",
}


class _PresentationValidationContext(NamedTuple):
    field_names: set[str]
    option_values: set[str]
    workflows: dict[str, dict[str, Any]]
    prefix: str


def _validate_object_manager_text_metadata(object_manager: dict[str, Any]) -> None:
    for text_field in ("activation", "production_impact_claim"):
        if text_field in object_manager and (
            not isinstance(object_manager[text_field], str)
            or not object_manager[text_field].strip()
        ):
            _fail(f"object_manager.{text_field} must be non-empty text")


def _validate_restart_required(object_manager: dict[str, Any]) -> None:
    if "restart_required" not in object_manager:
        return
    if object_manager["restart_required"].__class__ is not bool:
        _fail("object_manager.restart_required must be boolean")


def _validate_implementation_sequence(object_manager: dict[str, Any]) -> None:
    if "implementation_sequence" not in object_manager:
        return
    if not isinstance(object_manager["implementation_sequence"], list):
        _fail("object_manager.implementation_sequence must be a string list")
    for value in object_manager["implementation_sequence"]:
        if not isinstance(value, str):
            _fail("object_manager.implementation_sequence must be a string list")
        if not value.strip():
            _fail("object_manager.implementation_sequence must be a string list")


def _validate_object_manager_boolean_metadata(object_manager: dict[str, Any]) -> None:
    _validate_restart_required(object_manager)
    _validate_implementation_sequence(object_manager)


def _validate_object_manager_metadata(object_manager: dict[str, Any]) -> None:
    _validate_object_manager_text_metadata(object_manager)
    _validate_object_manager_boolean_metadata(object_manager)


def _object_field_name(
    collection: str, field: dict[str, Any], namespace: str
) -> str:
    _shape(
        field,
        f"object_manager.{collection} field",
        required={"name", "options", "type"},
        allowed=OBJECT_FIELD_FIELDS,
    )
    name = field.get("name")
    if (
        not isinstance(name, str)
        or not name.startswith(namespace)
        or field.get("type") not in {"select", "tree_select"}
    ):
        _fail(f"object_manager.{collection} has an invalid field")
    return name


def _object_field_options(field: dict[str, Any], name: str) -> list[str]:
    options = field.get("options")
    if not isinstance(options, list):
        _fail(f"object manager options must be unique strings: {name}")
    if not options:
        _fail(f"object manager options must be unique strings: {name}")
    for option in options:
        if not isinstance(option, str):
            _fail(f"object manager options must be unique strings: {name}")
        if not option:
            _fail(f"object manager options must be unique strings: {name}")
    if len(options) != len(set(options)):
        _fail(f"object manager options must be unique strings: {name}")
    return options


def _validate_object_field_booleans(field: dict[str, Any], name: str) -> None:
    for boolean_field in ("api_only", "required_by_workflow"):
        if boolean_field in field and field[boolean_field].__class__ is not bool:
            _fail(f"object manager {boolean_field} must be boolean: {name}")


def _record_ticket_field_options(
    collection: str,
    name: str,
    namespace: str,
    options: list[str],
    ticket_options: dict[str, set[str]],
) -> None:
    if collection != "ticket_fields":
        return
    logical_name = name.removeprefix(namespace)
    if not logical_name or logical_name in ticket_options:
        _fail(f"duplicate logical ticket field name: {name}")
    ticket_options[logical_name] = set(options)


def _validate_object_fields(
    object_manager: dict[str, Any], namespace: str
) -> tuple[set[str], set[str], dict[str, set[str]]]:
    field_names: set[str] = set()
    option_values: set[str] = set()
    ticket_options: dict[str, set[str]] = {}
    for collection in FIELD_COLLECTIONS:
        fields = object_manager[collection]
        if not isinstance(fields, list):
            _fail(f"object_manager.{collection} must be a list")
        for field in fields:
            name = _object_field_name(collection, field, namespace)
            if name in field_names:
                _fail(f"duplicate object manager field: {name}")
            field_names.add(name)
            options = _object_field_options(field, name)
            option_values.update(options)
            _validate_object_field_booleans(field, name)
            _record_ticket_field_options(
                collection, name, namespace, options, ticket_options
            )
    return field_names, option_values, ticket_options


def _validate_object_manager_tenant_default(object_manager: dict[str, Any]) -> None:
    tenant_default = _shape(
        object_manager["tenant_default"],
        "object_manager.tenant_default",
        required={"default", "hidden", "optional"},
        allowed={"default", "hidden", "no_date_or_datetime", "optional"},
    )
    _validate_tenant_default_hidden(tenant_default)
    _validate_tenant_default_optional(tenant_default)
    _validate_tenant_default_value(tenant_default)
    _validate_tenant_default_date_restriction(tenant_default)


def _validate_tenant_default_hidden(tenant_default: dict[str, Any]) -> None:
    if tenant_default.get("hidden") is not True:
        _fail("tenant defaults must be hidden, optional, null, and date-free")


def _validate_tenant_default_optional(tenant_default: dict[str, Any]) -> None:
    if tenant_default.get("optional") is not True:
        _fail("tenant defaults must be hidden, optional, null, and date-free")


def _validate_tenant_default_value(tenant_default: dict[str, Any]) -> None:
    if tenant_default.get("default", object()) is not None:
        _fail("tenant defaults must be hidden, optional, null, and date-free")


def _validate_tenant_default_date_restriction(tenant_default: dict[str, Any]) -> None:
    if tenant_default.get("no_date_or_datetime", True) is not True:
        _fail("tenant defaults must be hidden, optional, null, and date-free")


def _validate_core_workflow_context(workflow: dict[str, Any], key: str) -> None:
    if workflow.get("context") not in {
        "agent_create",
        "agent_edit",
        "customer_create",
    }:
        _fail(f"core workflow {key} has an invalid declarative contract")


def _validate_core_workflow_match(workflow: dict[str, Any], key: str) -> None:
    if not isinstance(workflow.get("match"), str):
        _fail(f"core workflow {key} has an invalid declarative contract")
    if not workflow["match"]:
        _fail(f"core workflow {key} has an invalid declarative contract")


def _validate_core_workflow_actions(workflow: dict[str, Any], key: str) -> None:
    if not isinstance(workflow.get("actions"), str):
        _fail(f"core workflow {key} has an invalid declarative contract")
    if not workflow["actions"]:
        _fail(f"core workflow {key} has an invalid declarative contract")


def _validate_core_workflows(object_manager: dict[str, Any]) -> dict[str, dict[str, Any]]:
    workflows = _keyed_items(object_manager["core_workflows"], "core workflows")
    for key, workflow in workflows.items():
        _shape(workflow, f"core workflow {key}", required=WORKFLOW_FIELDS)
        _validate_core_workflow_context(workflow, key)
        _validate_core_workflow_match(workflow, key)
        _validate_core_workflow_actions(workflow, key)
    return workflows


def _validate_presentation_map(mapping: Any, name: str) -> None:
    if not isinstance(mapping, dict):
        _fail(f"presentation {name} must be a non-empty-string map")
    for key, value in mapping.items():
        if not isinstance(key, str):
            _fail(f"presentation {name} must be a non-empty-string map")
        if not isinstance(value, str):
            _fail(f"presentation {name} must be a non-empty-string map")
        if not value.strip():
            _fail(f"presentation {name} must be a non-empty-string map")


def _validate_presentation_maps(presentation: dict[str, Any]) -> None:
    for name in ("field_labels", "option_labels", "core_workflow_names"):
        _validate_presentation_map(presentation[name], name)


def _validate_presentation_coverage(
    presentation: dict[str, Any],
    context: _PresentationValidationContext,
) -> None:
    if set(presentation["field_labels"]) != context.field_names:
        _fail("field labels must cover object manager fields exactly")
    if set(presentation["option_labels"]) != context.option_values:
        _fail("option labels must cover object manager options exactly")
    if set(presentation["core_workflow_names"]) != set(context.workflows):
        _fail("workflow names must cover core workflows exactly")
    if any(
        not name.startswith(context.prefix)
        for name in presentation["core_workflow_names"].values()
    ):
        _fail("core workflow names must start with managed_prefix")


def _validate_object_manager_position_shape(object_name: str, position: Any) -> None:
    if not isinstance(position, dict):
        _fail(f"object manager position for {object_name} is invalid")


def _validate_object_manager_position_keys(
    object_name: str, position: dict[str, Any]
) -> None:
    if set(position) != {"start", "step"}:
        _fail(f"object manager position for {object_name} is invalid")


def _validate_object_manager_position_values(
    object_name: str, position: dict[str, Any]
) -> None:
    for key in ("start", "step"):
        if position[key].__class__ is not int:
            _fail(f"object manager position for {object_name} is invalid")
        if not position[key] > 0:
            _fail(f"object manager position for {object_name} is invalid")


def _validate_object_manager_position(object_name: str, position: Any) -> None:
    _validate_object_manager_position_shape(object_name, position)
    _validate_object_manager_position_keys(object_name, position)
    _validate_object_manager_position_values(object_name, position)


def _validate_object_manager_positions(presentation: dict[str, Any]) -> None:
    positions = presentation["object_manager_positions"]
    if (
        not isinstance(positions, dict)
        or set(positions) != {"Group", "Organization", "Ticket", "User"}
    ):
        _fail("object manager positions must cover Ticket/User/Organization/Group")
    for object_name, position in positions.items():
        _validate_object_manager_position(object_name, position)


def _validate_object_manager_presentation(
    presentation: Any,
    context: _PresentationValidationContext,
) -> None:
    if not isinstance(presentation, dict) or set(presentation) != PRESENTATION_FIELDS:
        _fail("presentation must contain exactly the required fields")
    _validate_presentation_maps(presentation)
    _validate_presentation_coverage(presentation, context)
    _validate_object_manager_positions(presentation)


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
    _validate_object_manager_metadata(object_manager)
    field_names, option_values, ticket_options = _validate_object_fields(
        object_manager, namespace
    )
    _validate_object_manager_tenant_default(object_manager)
    workflows = _validate_core_workflows(object_manager)
    presentation_context = _PresentationValidationContext(
        field_names, option_values, workflows, prefix
    )
    _validate_object_manager_presentation(presentation, presentation_context)
    return ticket_options
