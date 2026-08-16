"""Profile UAT validation."""

from __future__ import annotations

from typing import Any, NamedTuple

from .profile_support import (
    HANDOFF_PROBE_FIELDS,
    JOB_PROBE_FIELDS,
    MANIFEST_UAT_FIELDS,
    PROFILE_UAT_FIELDS,
    SCENARIO_BASE_FIELDS,
    _fail,
    _keyed_items,
    _shape,
)


class _UatValidationContext(NamedTuple):
    leaf_keys: set[str]
    agents: dict[str, dict[str, Any]]
    customers: dict[str, dict[str, Any]]
    tags: set[str]
    jobs: dict[str, dict[str, Any]]
    ticket_options: dict[str, set[str]]


class _UatScenarioReferences(NamedTuple):
    scenarios: dict[str, dict[str, Any]]
    context: _UatValidationContext


def _validate_uat_contracts(
    profile_uat: Any, manifest_uat: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
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
    return profile_uat, manifest_uat


def _validate_uat_safety_contract(
    profile_uat: dict[str, Any], manifest_uat: dict[str, Any]
) -> None:
    for uat, label in ((profile_uat, "profile"), (manifest_uat, "manifest")):
        if (
            uat.get("article_visibility") != "internal"
            or uat.get("retention") != "close_and_retain"
            or uat.get("outbound_communication") is not False
        ):
            _fail(f"invalid {label} UAT safety contract")


def _validate_uat_title(profile_uat: dict[str, Any], manifest_uat: dict[str, Any]) -> None:
    if not isinstance(profile_uat.get("title_prefix"), str) or not profile_uat[
        "title_prefix"
    ]:
        _fail("profile UAT requires a title_prefix")
    if manifest_uat.get("title_prefix") != profile_uat["title_prefix"]:
        _fail("profile and manifest UAT title_prefix must match")


def _validate_uat_defaults(
    profile_uat: dict[str, Any], ticket_options: dict[str, set[str]]
) -> None:
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


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _has_valid_uat_scenario_core(
    scenario: dict[str, Any],
    leaf_keys: set[str],
    agents: dict[str, dict[str, Any]],
    customers: dict[str, dict[str, Any]],
) -> bool:
    return (
        _is_nonempty_string(scenario.get("kind"))
        and _is_nonempty_string(scenario.get("label"))
        and scenario.get("group") in leaf_keys
        and scenario.get("customer") in customers
        and scenario.get("agent") in agents
    )


def _validate_uat_scenario_core(
    key: str,
    scenario: dict[str, Any],
    context: _UatValidationContext,
) -> None:
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
        allowed=SCENARIO_BASE_FIELDS | set(context.ticket_options),
    )
    if not _has_valid_uat_scenario_core(
        scenario, context.leaf_keys, context.agents, context.customers
    ):
        _fail(f"invalid UAT scenario: {key}")


def _validate_uat_scenario_tags(
    key: str, scenario: dict[str, Any], tags: set[str]
) -> None:
    expected_tags = scenario.get("expected_tags")
    if not isinstance(expected_tags, list):
        _fail(f"invalid UAT scenario tags: {key}")
    if not expected_tags:
        _fail(f"invalid UAT scenario tags: {key}")
    if not all(isinstance(tag, str) for tag in expected_tags):
        _fail(f"invalid UAT scenario tags: {key}")
    if len(expected_tags) != len(set(expected_tags)):
        _fail(f"invalid UAT scenario tags: {key}")
    if not set(expected_tags).issubset(tags):
        _fail(f"invalid UAT scenario tags: {key}")


def _validate_uat_scenario_correlation(key: str, scenario: dict[str, Any]) -> None:
    correlation = scenario.get("correlation_template")
    if correlation is not None and (
        not isinstance(correlation, str) or correlation.count("{run}") != 1
    ):
        _fail(f"invalid UAT correlation template: {key}")
    if (
        "synthetic_attachment" in scenario
        and scenario["synthetic_attachment"].__class__ is not bool
    ):
        _fail(f"invalid UAT attachment flag: {key}")


def _validate_uat_scenario_options(
    key: str, scenario: dict[str, Any], ticket_options: dict[str, set[str]]
) -> None:
    for field, options in ticket_options.items():
        if field in scenario and (
            not isinstance(scenario[field], str) or scenario[field] not in options
        ):
            _fail(f"invalid UAT option override {field}: {key}")


def _validate_uat_scenario(
    key: str,
    scenario: dict[str, Any],
    context: _UatValidationContext,
) -> None:
    _validate_uat_scenario_core(key, scenario, context)
    _validate_uat_scenario_tags(key, scenario, context.tags)
    _validate_uat_scenario_correlation(key, scenario)
    _validate_uat_scenario_options(key, scenario, context.ticket_options)


def _validate_uat_scenarios(
    profile_uat: dict[str, Any],
    manifest_uat: dict[str, Any],
    context: _UatValidationContext,
) -> dict[str, dict[str, Any]]:
    scenarios = _keyed_items(profile_uat.get("scenarios"), "UAT scenarios")
    if manifest_uat.get("ticket_count") != len(scenarios):
        _fail("UAT ticket_count must equal scenario count")
    numbers = [scenario.get("number") for scenario in scenarios.values()]
    if (
        any(value.__class__ is not int or value < 1 for value in numbers)
        or len(numbers) != len(set(numbers))
    ):
        _fail("UAT scenario numbers must be positive and unique")
    for key, scenario in scenarios.items():
        _validate_uat_scenario(key, scenario, context)
    return scenarios


def _validate_uat_access_matrix(
    profile_uat: dict[str, Any], scenarios: dict[str, dict[str, Any]]
) -> list[str]:

    access_matrix = _shape(
        profile_uat.get("access_matrix"),
        "UAT access_matrix",
        required={"seed_keys"},
    )
    seed_keys = access_matrix["seed_keys"]
    _validate_uat_seed_keys(seed_keys, scenarios)
    return seed_keys


def _validate_uat_seed_keys(
    seed_keys: Any, scenarios: dict[str, dict[str, Any]]
) -> None:
    if (
        not isinstance(seed_keys, list)
        or not seed_keys
        or not all(isinstance(key, str) for key in seed_keys)
        or len(seed_keys) != len(set(seed_keys))
    ):
        _fail("UAT seed coverage invalid")
    _validate_uat_seed_coverage(seed_keys, scenarios)


def _validate_uat_seed_coverage(
    seed_keys: list[str], scenarios: dict[str, dict[str, Any]]
) -> None:
    if not set(seed_keys).issubset(scenarios) or any(
        scenarios[key].get("kind") != "seed" for key in seed_keys
    ):
        _fail("UAT seed coverage invalid")


def _validate_handoff_probe_references(
    handoff: dict[str, Any],
    references: _UatScenarioReferences,
) -> None:
    if not _has_known_handoff_probe_references(handoff, references):
        _fail("invalid handoff_probe contract")


def _has_known_handoff_probe_references(
    handoff: dict[str, Any],
    references: _UatScenarioReferences,
) -> bool:
    context = references.context
    return (
        handoff.get("ticket_key") in references.scenarios
        and handoff.get("agent") in context.agents
        and handoff.get("source_group") in context.leaf_keys
        and handoff.get("target_group") in context.leaf_keys
        and handoff.get("pending_tag") in context.tags
        and handoff.get("recorded_tag") in context.tags
    )


def _validate_handoff_probe_owner(handoff: dict[str, Any]) -> None:
    if handoff.get("expected_owner") != "unassigned":
        _fail("invalid handoff_probe contract")


def _validate_uat_handoff_probe(
    profile_uat: dict[str, Any],
    scenarios: dict[str, dict[str, Any]],
    context: _UatValidationContext,
) -> None:

    handoff = profile_uat.get("handoff_probe")
    if handoff is not None:
        _shape(handoff, "handoff_probe", required=HANDOFF_PROBE_FIELDS)
        _validate_handoff_probe_references(
            handoff, _UatScenarioReferences(scenarios, context)
        )
        _validate_handoff_probe_owner(handoff)


def _validate_job_probe_references(
    job_probe: dict[str, Any],
    references: _UatScenarioReferences,
) -> None:
    if (
        job_probe.get("ticket_key") not in references.scenarios
        or job_probe.get("agent") not in references.context.agents
        or job_probe.get("job_key") not in references.context.jobs
        or job_probe.get("marker_tag") not in references.context.tags
    ):
        _fail("invalid job_probe contract")


def _validate_job_probe_details(job_probe: dict[str, Any]) -> None:
    if not _has_valid_job_probe_details(job_probe):
        _fail("invalid job_probe contract")


def _is_positive_integer(value: Any) -> bool:
    return value.__class__ is int and value >= 1


def _has_valid_job_probe_details(job_probe: dict[str, Any]) -> bool:
    return (
        _is_nonempty_string(job_probe.get("subject"))
        and _is_positive_integer(job_probe.get("expected_internal_notes"))
        and _is_nonempty_string(job_probe.get("final_schedule"))
    )


def _validate_uat_job_probe(
    profile_uat: dict[str, Any],
    scenarios: dict[str, dict[str, Any]],
    context: _UatValidationContext,
) -> None:
    job_probe = profile_uat.get("job_probe")
    if job_probe is not None:
        _shape(job_probe, "job_probe", required=JOB_PROBE_FIELDS)
        _validate_job_probe_references(
            job_probe, _UatScenarioReferences(scenarios, context)
        )
        _validate_job_probe_details(job_probe)


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
    profile_uat, manifest_uat = _validate_uat_contracts(profile_uat, manifest_uat)
    context = _UatValidationContext(
        leaf_keys,
        agents,
        customers,
        tags,
        jobs,
        ticket_options,
    )
    _validate_uat_safety_contract(profile_uat, manifest_uat)
    _validate_uat_title(profile_uat, manifest_uat)
    _validate_uat_defaults(profile_uat, context.ticket_options)
    scenarios = _validate_uat_scenarios(profile_uat, manifest_uat, context)
    seed_keys = _validate_uat_access_matrix(profile_uat, scenarios)
    _validate_uat_handoff_probe(profile_uat, scenarios, context)
    _validate_uat_job_probe(profile_uat, scenarios, context)
    return scenarios, seed_keys
