"""Deterministic compilation of canonical V2 projects into a plan and capability graph."""

from __future__ import annotations

import copy
from typing import Any

from ..contracts.json import canonical_sha256
from ..planning import compile_validated_profile
from .errors import ProjectError
from .v1 import V1Snapshot
from .v2 import (
    ValidatedV2Project,
    migrate_v1_snapshot,
    require_enabled_decision_dependencies,
    validate_v2_snapshot,
)

RESOURCE_CAPABILITIES = {
    "agents": "uat-evidence",
    "checklist_templates": "overviews-macros-templates-text-modules-checklists",
    "core_workflows": "fields-core-workflows",
    "customers": "uat-evidence",
    "groups": "service-topology",
    "jobs": "triggers-schedulers-report-profiles",
    "macros": "overviews-macros-templates-text-modules-checklists",
    "object_manager_fields": "fields-core-workflows",
    "organizations": "organizations-customers",
    "overviews": "overviews-macros-templates-text-modules-checklists",
    "report_profiles": "triggers-schedulers-report-profiles",
    "roles": "roles-acl",
    "tags": "tags",
    "triggers": "triggers-schedulers-report-profiles",
    "uat_scenarios": "uat-evidence",
}


def compile_v2_project(project: Any) -> dict[str, Any]:
    """Validate V2 and compile its unchanged V1 bundle plus an inert graph."""
    return _compile_validated(validate_v2_snapshot(project))


def compile_v1_snapshot(snapshot: V1Snapshot) -> dict[str, Any]:
    """Compile an already validated V1 snapshot to canonical V2 without revalidating it."""
    migrated = migrate_v1_snapshot(snapshot)
    require_enabled_decision_dependencies(migrated["workbook"]["capability_decisions"])
    return _compile_validated(ValidatedV2Project(migrated, snapshot.profile_summary))


def _compile_validated(validated: ValidatedV2Project) -> dict[str, Any]:
    normalized = validated.project
    bundle = normalized["bundle"]
    plan = compile_validated_profile(
        {"profile": bundle["profile"], "manifest": bundle["manifest"]},
        validated.profile_summary,
    )
    decisions = normalized["workbook"]["capability_decisions"]
    owner = normalized["workbook"]["organization"].get("service_owner_role", "unassigned")
    nodes = _capability_nodes(decisions, owner)
    nodes.extend(_operation_nodes(plan, bundle, decisions))
    graph: dict[str, Any] = {"nodes": nodes}
    graph["graph_hash"] = canonical_sha256(graph)
    return {
        "project": normalized,
        "bundle": copy.deepcopy(bundle),
        "plan": plan,
        "graph": graph,
        "hashes": {
            "profile": plan["source_hashes"]["profile"],
            "manifest": plan["source_hashes"]["manifest"],
            "plan": plan["plan_hash"],
            "project": canonical_sha256(normalized),
            "graph": graph["graph_hash"],
        },
    }


def _capability_nodes(decisions: dict[str, dict[str, Any]], owner: Any) -> list[dict[str, Any]]:
    if not isinstance(owner, str) or not owner:
        owner = "unassigned"
    return [
        {
            "id": f"capability:{capability_id}",
            "resource_kind": "capability_gate",
            "logical_key": capability_id,
            "desired": {
                "enabled": decision["enabled"],
                "completion": decision["completion"],
            },
            "dependencies": [
                f"capability:{dependency}"
                for dependency in decision["dependencies"]
            ],
            "delivery": decision["delivery"],
            "risk": decision["risk"],
            "owner": owner,
            "verification": {
                "mode": "decision_evidence",
                "required": decision["enabled"],
            },
            "rollback": {
                "strategy": "no_tenant_mutation",
                "destructive": False,
            },
        }
        for capability_id, decision in sorted(decisions.items())
    ]


def _operation_nodes(
    plan: dict[str, Any], bundle: dict[str, Any], decisions: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for operation in plan["operations"]:
        owner = bundle["resource_ownership"].get(operation["id"], "core")
        capability = RESOURCE_CAPABILITIES.get(operation["resource"])
        if capability is None:
            raise ProjectError(
                "configuration graph has no capability mapping for resource "
                f"{operation['resource']}"
            )
        decision = decisions[capability]
        if not decision["enabled"]:
            raise ProjectError(
                f"configuration graph requires enabled capability {capability} "
                f"for operation {operation['id']}"
            )
        automated = decision["delivery"] == "automated"
        rollback_strategy = (
            "retain_and_review"
            if operation["action"] == "ensure_present"
            else "deactivate_created_resource"
            if automated
            else "manual_recovery_plan"
        )
        nodes.append(
            {
                "id": operation["id"],
                "resource_kind": operation["resource"],
                "logical_key": operation["key"],
                "desired": operation["desired_state"],
                "dependencies": [
                    f"capability:{capability}",
                    *operation["depends_on"],
                ],
                "delivery": decision["delivery"],
                "risk": decision["risk"],
                "owner": owner,
                "verification": {
                    "mode": "compiled_postcondition" if automated else "guided_evidence",
                    "desired_hash": canonical_sha256(operation["desired_state"]),
                },
                "rollback": {
                    "strategy": rollback_strategy,
                    "destructive": False,
                },
            }
        )
    return nodes
