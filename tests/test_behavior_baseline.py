"""Golden characterization of externally observable CLI and Studio API behavior.

The expected values in ``fixtures/behavior-baseline.json`` were recorded from
the pre-reconstruction implementation. They pin response status codes, error
envelopes, and canonical payload hashes for every documented route and both
packaged examples. Regenerate them only for a deliberate, documented contract
change:

    python3 -m tests.test_behavior_baseline --regenerate
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

from queuewright import compile_plan, validate_profile
from queuewright.cli import main
from queuewright.contracts.json import canonical_sha256
from queuewright.studio import StudioService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "queuewright" / "examples"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "behavior-baseline.json"
MANIFESTS = {"minimal": "desired-state.json", "university": "university.desired-state.json"}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _bundle(name: str) -> dict[str, Any]:
    return {
        "profile": _read(EXAMPLES / name / "profile.json"),
        "manifest": _read(EXAMPLES / name / MANIFESTS[name]),
    }


def _editable_draft(project: dict[str, Any]) -> dict[str, Any]:
    """Mirror studio-ui editableV2Draft: only authored V2 fields."""
    return {
        "project_schema_version": "2.0",
        "id": project["id"],
        "name": project["name"],
        "target_schema_version": project["target_schema_version"],
        "workbook": {
            "organization": project["workbook"]["organization"],
            "capability_decisions": {
                key: {"enabled": value["enabled"], "completion": value["completion"]}
                for key, value in project["workbook"]["capability_decisions"].items()
            },
        },
        "extensions": project["extensions"],
        "bundle": project["bundle"],
    }


def _summarize(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    if status != 200:
        return {"status": status, "payload": payload}
    return {"status": status, "sha256": canonical_sha256(payload), "keys": sorted(payload)}


def _cli(argv: list[str]) -> dict[str, Any]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = main(argv)
        except SystemExit as exit_:
            code = exit_.code
    out = stdout.getvalue()
    return {"exit": code, "stdout_sha256": canonical_sha256(out), "stderr_tail": stderr.getvalue().strip().splitlines()[-1:]}


def _mutated(base: dict[str, Any], mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    value = copy.deepcopy(base)
    mutate(value)
    return value


def _failure_cases(service: StudioService) -> dict[str, tuple[str, str, Any]]:
    bundle = _bundle("minimal")
    _, imported = service.dispatch("POST", "/api/v1/import-bundle", copy.deepcopy(bundle))
    v1 = imported["project"]
    _, migrated = service.dispatch("POST", "/api/v2/migrate-project", {"project": copy.deepcopy(v1)})
    v2 = migrated["project"]

    def set_path(*path: Any, value: Any) -> Callable[[dict[str, Any]], None]:
        def apply(target: dict[str, Any]) -> None:
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
        return apply

    def delete_path(*path: Any) -> Callable[[dict[str, Any]], None]:
        def apply(target: dict[str, Any]) -> None:
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
        return apply

    first_group = next(key for key in v1["resource_ownership"] if key.startswith("groups:"))
    first_role = next(key for key in v1["resource_ownership"] if key.startswith("roles:"))
    return {
        "unknown_get": ("GET", "/api/v1/unknown", None),
        "unknown_post": ("POST", "/api/v3/compile", {}),
        "other_get": ("GET", "/elsewhere", None),
        "bundle_not_object": ("POST", "/api/v1/import-bundle", []),
        "bundle_missing_manifest": ("POST", "/api/v1/import-bundle", {"profile": {}}),
        "bundle_extra_field": ("POST", "/api/v1/import-bundle", {**bundle, "extra": 1}),
        "bundle_profile_not_object": ("POST", "/api/v1/import-bundle", {"profile": [], "manifest": {}}),
        "bundle_invalid_safety": ("POST", "/api/v1/import-bundle", _mutated(bundle, set_path("manifest", "safety_contract", "allow_delete", value=True))),
        "compile_bundle_invalid": ("POST", "/api/v2/compile", _mutated(bundle, set_path("profile", "offline_only", value=False))),
        "v1_compile_not_wrapped": ("POST", "/api/v1/compile-project", v1),
        "v1_project_not_object": ("POST", "/api/v1/compile-project", {"project": []}),
        "v1_missing_field": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, delete_path("feature_state"))}),
        "v1_unknown_field": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("extra", value=1))}),
        "v1_bad_schema_version": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("project_schema_version", value="9.9"))}),
        "v1_bad_id": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("id", value="../x"))}),
        "v1_empty_name": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("name", value=" "))}),
        "v1_target_mismatch": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("target_schema_version", value="1.1"))}),
        "v1_missing_ownership": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, delete_path("resource_ownership", first_group))}),
        "v1_extra_ownership": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("resource_ownership", "groups:nope", value="core"))}),
        "v1_bad_owner": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("resource_ownership", first_role, value="nobody"))}),
        "v1_ownership_not_object": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("resource_ownership", value=[]))}),
        "v1_feature_state_incomplete": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, delete_path("feature_state", "macros"))}),
        "v1_feature_state_shape": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("feature_state", "macros", value={"enabled": "yes", "settings": {}}))}),
        "v1_locked_disabled": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("feature_state", "access_matrix", "enabled", value=False))}),
        "v1_unsafe_settings": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("feature_state", "macros", "settings", value={"api_key": "x"}))}),
        "v1_url_settings": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("feature_state", "macros", "settings", value={"link": "https://example.invalid"}))}),
        "v1_disabled_dependency": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("feature_state", "triggers", "enabled", value=False))}),
        "v1_disabled_owner": ("POST", "/api/v1/compile-project", {"project": _mutated(v1, set_path("feature_state", "report_profiles", "enabled", value=False))}),
        "v2_migrate_not_wrapped": ("POST", "/api/v2/migrate-project", v1),
        "v2_migrate_invalid": ("POST", "/api/v2/migrate-project", {"project": _mutated(v1, set_path("id", value="Bad"))}),
        "v2_compile_project_not_wrapped": ("POST", "/api/v2/compile-project", v2),
        "v2_shape": ("POST", "/api/v2/compile", {"project": {"project_schema_version": "2.0"}}),
        "v2_bad_header": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("id", value="Bad Id"))}),
        "v2_target_mismatch": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("target_schema_version", value="1.1"))}),
        "v2_extensions_not_object": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("extensions", value=[]))}),
        "v2_extensions_unsafe": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("extensions", value={"token": "x"}))}),
        "v2_workbook_shape": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("workbook", value={}))}),
        "v2_organization_unsafe": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("workbook", "organization", "api_key", value="x"))}),
        "v2_decisions_incomplete": ("POST", "/api/v2/compile", {"project": _mutated(v2, delete_path("workbook", "capability_decisions", "tags"))}),
        "v2_decision_applied": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("workbook", "capability_decisions", "tags", "completion", value="applied"))}),
        "v2_decision_bad_enabled": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("workbook", "capability_decisions", "tags", "enabled", value=1))}),
        "v2_decision_dependency": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("workbook", "capability_decisions", "organization", "enabled", value=False))}),
        "v2_capability_disabled_for_ops": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("workbook", "capability_decisions", "tags", "enabled", value=False))}),
        "v2_derived_bad_shape": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("workbook", "services", value={}))}),
        "v2_bad_owner": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("bundle", "resource_ownership", first_role, value="nobody"))}),
        "v2_feature_state_bad_entry": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("bundle", "feature_state", "macros", value={"enabled": True}))}),
        "v2_bundle_shape": ("POST", "/api/v2/compile", {"project": _mutated(v2, delete_path("bundle", "feature_state"))}),
        "v2_bundle_invalid_profile": ("POST", "/api/v2/compile", {"project": _mutated(v2, set_path("bundle", "profile", "offline_only", value=False))}),
        "v2_editor_invalid": ("POST", "/api/v2/compile-editor", {"project": _mutated(v2, set_path("extensions", value=[]))}),
        "too_deep_body": ("POST", "/api/v2/compile", json.loads("[" * 70 + "]" * 70)),
    }


def collect() -> dict[str, Any]:
    service = StudioService()
    observed: dict[str, Any] = {}
    status, payload = service.dispatch("GET", "/api/v1/health")
    observed["health"] = _summarize(status, payload)
    status, payload = service.dispatch("GET", "/api/v1/catalog")
    observed["catalog"] = _summarize(status, payload)
    for name in sorted(MANIFESTS):
        bundle = _bundle(name)
        example = _read(EXAMPLES / name / "project-v2.json")
        observed[f"{name}:validate"] = canonical_sha256(validate_profile(EXAMPLES / name))
        observed[f"{name}:plan"] = canonical_sha256(compile_plan(EXAMPLES / name))
        observed[f"{name}:cli:validate"] = _cli(["validate", str(EXAMPLES / name)])
        observed[f"{name}:cli:plan"] = _cli(["plan", str(EXAMPLES / name / "profile.json")])
        routes: list[tuple[str, str, Any]] = []
        status, imported = service.dispatch("POST", "/api/v1/import-bundle", copy.deepcopy(bundle))
        observed[f"{name}:import-bundle"] = _summarize(status, imported)
        v1 = imported["project"]
        status, migrated = service.dispatch("POST", "/api/v2/migrate-project", {"project": copy.deepcopy(v1)})
        observed[f"{name}:migrate-project"] = _summarize(status, migrated)
        routes = [
            ("v1:compile-project", "/api/v1/compile-project", {"project": v1}),
            ("v2:compile-project", "/api/v2/compile-project", {"project": migrated["project"]}),
            ("v2:compile:bundle", "/api/v2/compile", bundle),
            ("v2:compile:v1", "/api/v2/compile", {"project": v1}),
            ("v2:compile:example", "/api/v2/compile", {"project": example}),
            ("v2:compile:draft", "/api/v2/compile", {"project": _editable_draft(example)}),
            ("v2:compile-editor:draft", "/api/v2/compile-editor", {"project": _editable_draft(example)}),
            ("v2:compile-editor:bundle", "/api/v2/compile-editor", bundle),
        ]
        for label, path, body in routes:
            status, payload = service.dispatch("POST", path, copy.deepcopy(body))
            observed[f"{name}:{label}"] = _summarize(status, payload)
    for label, (method, path, body) in _failure_cases(service).items():
        status, payload = service.dispatch(method, path, body)
        observed[f"failure:{label}"] = _summarize(status, payload)
    return observed


class BehaviorBaselineTests(unittest.TestCase):
    maxDiff = None

    def test_observable_behavior_matches_recorded_baseline(self) -> None:
        expected = _read(FIXTURE)
        observed = collect()
        self.assertEqual(sorted(observed), sorted(expected))
        for key in sorted(expected):
            with self.subTest(case=key):
                self.assertEqual(observed[key], expected[key])


if __name__ == "__main__":
    if "--regenerate" in sys.argv:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(collect(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {FIXTURE.relative_to(ROOT)}")
    else:
        unittest.main()
