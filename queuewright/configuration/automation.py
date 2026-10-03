"""Trigger, job, and report profile validation."""

from __future__ import annotations

from typing import Any

from .rules import _action_parts, _fail, _managed_names, _shape

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
ALLOWED_AUTOMATION_ACTIONS = {"add_tag", "internal_note"}
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


def _validate_automation_item_shape(
    item: dict[str, Any], label: str, key: str
) -> None:
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
        return
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


def _validate_automation_conditions(
    item: dict[str, Any], label: str, key: str
) -> None:
    condition_map = _shape(
        item.get("conditions"),
        f"{label} {key} conditions",
        required={"all"},
    )
    conditions = condition_map["all"]
    if not isinstance(conditions, list) or not all(
        isinstance(value, str) for value in conditions
    ):
        _fail(f"{label} {key} conditions must be a string list")
    has_group = any(
        condition in {"group in H", "group in S"} for condition in conditions
    )
    if not has_group or "organization in O" not in conditions:
        _fail(f"{label} {key} lacks required H/S and O fence")


def _validate_automation_effects(
    item: dict[str, Any], label: str, key: str
) -> None:
    if label == "trigger" and item.get("external_effects") is not False:
        _fail(f"trigger {key} must explicitly disable external effects")
    if label == "job" and item.get("external_effects", False) is not False:
        _fail(f"job {key} has external effects")


def _validate_automation_action(
    action: str, label: str, key: str, tags: set[str]
) -> None:
    verb, argument = _action_parts(action, f"{label} {key}")
    if verb not in ALLOWED_AUTOMATION_ACTIONS:
        _fail(f"{label} {key} has unsupported action: {verb}")
    if verb == "add_tag" and argument not in tags:
        _fail(f"{label} {key} adds an undeclared tag")


def _validate_automation_actions(
    item: dict[str, Any], label: str, key: str, tags: set[str]
) -> None:
    actions = item.get("actions")
    if not isinstance(actions, list) or not actions or not all(
        isinstance(action, str) for action in actions
    ):
        _fail(f"{label} {key} actions must be a non-empty string list")
    for action in actions:
        _validate_automation_action(action, label, key, tags)


def _validate_automation_optional_text(
    item: dict[str, Any], label: str, key: str
) -> None:
    for optional_text in ("idempotency", "schedule_note"):
        if optional_text in item and (
            not isinstance(item[optional_text], str)
            or not item[optional_text].strip()
        ):
            _fail(f"{label} {key} {optional_text} must be non-empty text")


def _validate_job_forbidden_actions(forbidden: Any, key: str) -> None:
    if not isinstance(forbidden, list):
        _fail(f"job {key} must declare schedule and all forbidden actions")
    for action in forbidden:
        if not isinstance(action, str):
            _fail(f"job {key} must declare schedule and all forbidden actions")
    if not FORBIDDEN_ACTIONS.issubset(set(forbidden)):
        _fail(f"job {key} must declare schedule and all forbidden actions")


def _validate_job_schedule(item: dict[str, Any], key: str) -> None:
    if not isinstance(item.get("schedule"), str):
        _fail(f"job {key} must declare schedule and all forbidden actions")
    if not item["schedule"]:
        _fail(f"job {key} must declare schedule and all forbidden actions")


def _validate_job_automation(item: dict[str, Any], key: str) -> None:
    _validate_job_forbidden_actions(item.get("forbidden_actions"), key)
    _validate_job_schedule(item, key)


def _validate_automation_item(
    item: dict[str, Any], label: str, key: str, tags: set[str]
) -> None:
    _validate_automation_item_shape(item, label, key)
    _validate_automation_conditions(item, label, key)
    _validate_automation_effects(item, label, key)
    _validate_automation_actions(item, label, key, tags)
    if item.get("active") is not True:
        _fail(f"{label} {key} must declare its desired active state")
    _validate_automation_optional_text(item, label, key)
    if label == "job":
        _validate_job_automation(item, key)


def _validate_automation(
    items: dict[str, dict[str, Any]],
    label: str,
    prefix: str,
    tags: set[str],
) -> None:
    _managed_names(items, label, prefix)
    for key, item in items.items():
        _validate_automation_item(item, label, key, tags)


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
