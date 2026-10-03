"""Regression coverage for bounded compiler performance optimizations."""

from __future__ import annotations

import copy
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from queuewright.configuration import load_profile, validate_loaded_profile
from queuewright.errors import ConfigurationError
from queuewright.planning import compile_loaded_profile
from queuewright.planning import compiler as planning_compiler
from queuewright.planning.compiler import _dependency_order
from queuewright.projects import bundle as project_bundle
from queuewright.projects import compile_v2_project
from queuewright.projects import registry as project_registry
from queuewright.studio import StudioService

ROOT = Path(__file__).resolve().parents[1]


def _loaded_example(name: str) -> dict[str, object]:
    directory = ROOT / "queuewright" / "examples" / name
    manifest_name = (
        "university.desired-state.json" if name == "university" else "desired-state.json"
    )
    return {
        "profile": json.loads((directory / "profile.json").read_text(encoding="utf-8")),
        "manifest": json.loads((directory / manifest_name).read_text(encoding="utf-8")),
    }


def _project_example(name: str = "university") -> dict[str, object]:
    path = ROOT / "queuewright" / "examples" / name / "project-v2.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _legacy_dependency_order(operations: list[dict[str, object]]) -> list[str]:
    remaining = {operation["id"]: operation for operation in operations}
    complete: set[str] = set()
    ordered: list[str] = []
    while remaining:
        ready = [
            operation
            for operation in remaining.values()
            if set(operation["depends_on"]) <= complete
        ]
        if not ready:
            raise ConfigurationError("symbolic plan contains a dependency cycle")
        for operation in sorted(ready, key=lambda value: value["id"]):
            operation_id = str(operation["id"])
            ordered.append(operation_id)
            complete.add(operation_id)
            del remaining[operation_id]
    return ordered


class CompilationOptimizationTests(unittest.TestCase):
    def test_randomized_dags_preserve_sorted_wave_order(self) -> None:
        randomizer = random.Random(20260908)
        for size in (1, 2, 7, 31, 97):
            for _ in range(12):
                operations: list[dict[str, object]] = []
                ids = [f"node:{index:03d}" for index in range(size)]
                for index, operation_id in enumerate(ids):
                    candidates = ids[:index]
                    dependencies = randomizer.sample(
                        candidates, randomizer.randrange(min(5, len(candidates)) + 1)
                    )
                    operations.append(
                        {"id": operation_id, "depends_on": dependencies}
                    )
                randomizer.shuffle(operations)
                expected = _legacy_dependency_order(copy.deepcopy(operations))
                actual = _dependency_order(copy.deepcopy(operations))
                self.assertEqual([operation["id"] for operation in actual], expected)
                self.assertEqual(
                    [operation["sequence"] for operation in actual],
                    list(range(1, size + 1)),
                )

    def test_deep_group_hierarchy_validates_and_cycles_still_fail_closed(self) -> None:
        loaded = _loaded_example("university")
        groups = loaded["manifest"]["groups"]  # type: ignore[index]
        parent = "university"
        for index in range(2_000):
            key = f"chain_{index:04d}"
            groups.append(  # type: ignore[union-attr]
                {
                    "key": key,
                    "name": f"University Template · Chain {index:04d}",
                    "parent": parent,
                    "kind": "container",
                    "active": True,
                }
            )
            parent = key
        summary = validate_loaded_profile(loaded)  # type: ignore[arg-type]
        self.assertEqual(summary["counts"]["containers"], 2_004)

        cyclic = copy.deepcopy(loaded)
        cyclic["manifest"]["groups"][11]["parent"] = "chain_1999"  # type: ignore[index]
        with self.assertRaisesRegex(
            ConfigurationError, "group hierarchy contains a cycle at: chain_0000"
        ):
            validate_loaded_profile(cyclic)  # type: ignore[arg-type]

    def test_generated_v1_cannot_skip_capability_dependency_validation(self) -> None:
        loaded = _loaded_example("minimal")
        for collection in ("ticket_fields", "user_fields", "organization_fields", "group_fields", "core_workflows"):
            loaded["manifest"]["object_manager"][collection] = []
        for field in ("field_labels", "option_labels", "core_workflow_names"):
            loaded["profile"]["presentation"][field] = {}
        loaded["profile"]["uat"]["defaults"] = {}
        validate_loaded_profile(loaded)
        service = StudioService()
        status, error = service.dispatch("POST", "/api/v2/compile", loaded)
        self.assertEqual(status, 422)
        self.assertIn("requires enabled dependency fields-core-workflows", error["message"])
        _, imported = service.dispatch("POST", "/api/v1/import-bundle", loaded)
        status, error = service.dispatch("POST", "/api/v2/compile", {"project": imported["project"]})
        self.assertEqual(status, 422)

    def test_public_compilers_still_validate_malformed_inputs(self) -> None:
        with self.assertRaises(ConfigurationError):
            compile_loaded_profile({"profile": {}, "manifest": {}})
        with self.assertRaisesRegex(ConfigurationError, "project must contain exactly"):
            compile_v2_project({"project_schema_version": "2.0"})

    def test_profile_loader_bounds_depth_and_long_integer_parse_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = "{}"
            for _ in range(65):
                nested = '{"child":' + nested + "}"
            (root / "profile.json").write_text(nested, encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "64 nesting levels"):
                load_profile(root / "profile.json")

            (root / "profile.json").write_text(
                '{"value":' + ("9" * 10_000) + "}", encoding="utf-8"
            )
            with self.assertRaisesRegex(ConfigurationError, "cannot read JSON"):
                load_profile(root / "profile.json")

    def test_editor_compile_validates_once_reuses_registries_and_detaches_bundles(self) -> None:
        project = _project_example()
        original_name = project["bundle"]["manifest"]["groups"][0]["name"]  # type: ignore[index]
        service = StudioService()
        status, _ = service.dispatch("POST", "/api/v2/compile", {"project": copy.deepcopy(project)})
        self.assertEqual(status, 200)

        registry_paths = {
            project_registry.FEATURE_CATALOG_PATH,
            project_registry.CAPABILITY_REGISTRY_PATH,
        }
        registry_reads: list[Path] = []
        read_text = Path.read_text

        def counting_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path in registry_paths:
                registry_reads.append(path)
            return read_text(path, *args, **kwargs)  # type: ignore[arg-type]

        validate = Mock(wraps=validate_loaded_profile)
        with (
            patch.object(project_bundle, "validate_loaded_profile", validate),
            patch.object(planning_compiler, "validate_loaded_profile", validate),
            patch.object(Path, "read_text", counting_read_text),
        ):
            status, result = service.dispatch(
                "POST", "/api/v2/compile", {"project": project}
            )
        self.assertEqual(status, 200)
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(registry_reads, [])

        project["bundle"]["manifest"]["groups"][0]["name"] = "changed input"  # type: ignore[index]
        self.assertEqual(
            result["project"]["bundle"]["manifest"]["groups"][0]["name"],
            original_name,
        )
        result["bundle"]["manifest"]["groups"][0]["name"] = "changed result bundle"
        self.assertEqual(
            result["project"]["bundle"]["manifest"]["groups"][0]["name"],
            original_name,
        )


if __name__ == "__main__":
    unittest.main()
