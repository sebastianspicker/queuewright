"""Published JSON Schema parity with Queuewright's offline V2 contract."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

from queuewright.contracts.safety import SafeJsonError, validate_safe_json
from queuewright.studio import StudioService

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIRECTORY = ROOT / "queuewright" / "contracts" / "schemas"
EXAMPLE_DIRECTORY = ROOT / "queuewright" / "examples"
BUNDLE_FILES = (
    ("minimal", "profile.json", "desired-state.json"),
    ("university", "profile.json", "university.desired-state.json"),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class PublishedSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {
            path.name: load_json(path) for path in sorted(SCHEMA_DIRECTORY.glob("*.schema.json"))
        }
        cls.registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in cls.schemas.values()
        )
        cls.v2_validator = Draft202012Validator(
            cls.schemas["queuewright-project-v2.schema.json"], registry=cls.registry
        )

    def validator(self, name: str) -> Draft202012Validator:
        return Draft202012Validator(self.schemas[name], registry=self.registry)

    def test_all_published_schemas_meta_validate(self) -> None:
        for name, schema in self.schemas.items():
            with self.subTest(schema=name):
                Draft202012Validator.check_schema(schema)

    def test_canonical_v2_examples_validate_with_offline_local_refs(self) -> None:
        for name in ("minimal", "university"):
            with self.subTest(example=name):
                project = load_json(EXAMPLE_DIRECTORY / name / "project-v2.json")
                self.v2_validator.validate(project)

    def test_packaged_profiles_and_manifests_validate_against_their_schemas(self) -> None:
        profile_validator = self.validator("queuewright-profile.schema.json")
        manifest_validator = self.validator("queuewright-desired-state.schema.json")
        for name, profile_file, manifest_file in BUNDLE_FILES:
            with self.subTest(example=name):
                profile_validator.validate(load_json(EXAMPLE_DIRECTORY / name / profile_file))
                manifest_validator.validate(load_json(EXAMPLE_DIRECTORY / name / manifest_file))

    def test_v1_import_bundle_project_validates_against_the_v1_project_schema(self) -> None:
        validator = self.validator("queuewright-project.schema.json")
        for name, profile_file, manifest_file in BUNDLE_FILES:
            with self.subTest(example=name):
                body = {
                    "profile": load_json(EXAMPLE_DIRECTORY / name / profile_file),
                    "manifest": load_json(EXAMPLE_DIRECTORY / name / manifest_file),
                }
                status, response = StudioService().dispatch(
                    "POST", "/api/v1/import-bundle", body
                )
                self.assertEqual(status, 200)
                validator.validate(response["project"])

    def test_editor_compile_response_validates_against_its_schema(self) -> None:
        validator = self.validator("queuewright-editor-compile.schema.json")
        for name, profile_file, manifest_file in BUNDLE_FILES:
            with self.subTest(example=name):
                body = {
                    "profile": load_json(EXAMPLE_DIRECTORY / name / profile_file),
                    "manifest": load_json(EXAMPLE_DIRECTORY / name / manifest_file),
                }
                status, response = StudioService().dispatch(
                    "POST", "/api/v2/compile-editor", body
                )
                self.assertEqual(status, 200)
                validator.validate(response)

    def test_safe_json_failures_are_rejected_at_each_published_safe_object(self) -> None:
        fixture = load_json(EXAMPLE_DIRECTORY / "minimal" / "project-v2.json")
        cases = (
            ("workbook.organization", ("workbook", "organization"), "api_key"),
            ("extensions", ("extensions",), "password"),
            ("nested extensions object", ("extensions", "nested"), "token"),
        )
        for location, path, forbidden_key in cases:
            with self.subTest(location=location, key=forbidden_key):
                project = copy.deepcopy(fixture)
                target: dict[str, Any] = project
                for part in path:
                    target = target.setdefault(part, {})
                target[forbidden_key] = "not-allowed"
                with self.assertRaises(SafeJsonError):
                    validate_safe_json(project["workbook"] if path[0] == "workbook" else project["extensions"], path[0])
                with self.assertRaises(ValidationError):
                    self.v2_validator.validate(project)

    def test_safe_json_url_values_are_rejected_recursively(self) -> None:
        project = load_json(EXAMPLE_DIRECTORY / "minimal" / "project-v2.json")
        project["extensions"] = {"nested": {"endpoint": "https://example.invalid"}}
        with self.assertRaises(SafeJsonError):
            validate_safe_json(project["extensions"], "extensions")
        with self.assertRaises(ValidationError):
            self.v2_validator.validate(project)

    def test_capability_registry_mirrors_are_typed(self) -> None:
        project = load_json(EXAMPLE_DIRECTORY / "minimal" / "project-v2.json")
        for field, value in (
            ("delivery", "invalid"),
            ("risk", "invalid"),
            ("dependencies", ["not-a-capability"]),
            ("dependencies", ["organization", "organization"]),
        ):
            with self.subTest(field=field):
                invalid = copy.deepcopy(project)
                invalid["workbook"]["capability_decisions"]["organization"][field] = value
                with self.assertRaises(ValidationError):
                    self.v2_validator.validate(invalid)


if __name__ == "__main__":
    unittest.main()
