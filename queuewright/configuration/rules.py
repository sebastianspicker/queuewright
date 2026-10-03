"""Generic, I/O-free configuration checks and shared vocabularies."""

from __future__ import annotations

import re
from typing import Any, NoReturn

from ..errors import ConfigurationError

RESOURCE_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
PROFILE_KEY = re.compile(r"^[a-z][a-z0-9_-]*$")
MANIFEST_KEY = re.compile(r"^[a-z][a-z0-9_-]*-v[0-9]+$")
NAMESPACE = re.compile(r"^[a-z][a-z0-9_]*_$")
ARGUMENT_ACTIONS = {"add_tag", "internal_note", "set_group"}
FIELD_COLLECTIONS = (
    "ticket_fields",
    "user_fields",
    "organization_fields",
    "group_fields",
)
SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1.1"}


def _fail(message: str) -> NoReturn:
    raise ConfigurationError(message)


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
        _fail(f"{label} misses required field: {min(missing)}")
    if unknown:
        _fail(f"{label} has unsupported field: {min(unknown)}")
    return value


def _reject_url_values(value: Any, label: str = "configuration") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_url_values(child, f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_url_values(child, f"{label}[{index}]")
    elif isinstance(value, str) and re.search(r"\b(?:https?|wss?)://", value, re.IGNORECASE):
        _fail(f"{label} must not contain a URL")


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
        _fail(f"{label} references unknown key: {min(unknown)}")
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
