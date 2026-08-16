"""Offline contract tests for the reusable Zammad configuration package."""

from __future__ import annotations

import ast
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import queuewright.compiler as compiler_module
import queuewright.profile_automation as profile_automation
from queuewright.cli import main
from queuewright.compiler import compile_plan
from queuewright.errors import ConfigurationError
from queuewright.profile import load_profile, validate_profile


ROOT = Path(__file__).resolve().parents[1]
LEGACY_FIXTURE_PLAN_HASH = (
    "77ccef1e3ab8877f83668dadbfc3fe74addd7e5209069f55fb3ecc65f34ff395"
)
_CORE_WORKFLOW_CONTRACT_ERROR = (
    "core workflow agent_create_shared has an invalid declarative contract"
)
_CORE_WORKFLOW_MISSING_FIELDS = ("context", "match", "actions")
_CORE_WORKFLOW_INVALID_VALUES = (
    ("invalid context", "context", "agent_delete"),
    ("non-string match", "match", None),
    ("empty match", "match", ""),
    ("non-string actions", "actions", None),
    ("empty actions", "actions", ""),
)


def fixture_bundle(
    *, agent_count: int = 2, scenario_count: int = 3
) -> tuple[dict[str, Any], dict[str, Any]]:
    groups = [
        {
            "active": True,
            "key": "root",
            "kind": "container",
            "name": "Example · Root",
        },
        {
            "active": True,
            "key": "help",
            "kind": "leaf",
            "name": "Example · Help",
            "parent": "root",
            "service_code": "GEN.HELP",
        },
    ]
    agents = [
        {"key": f"agent{index}", "role": "support"}
        for index in range(agent_count)
    ]
    scenarios = [
        {
            "agent": f"agent{index % agent_count}",
            "customer": "customer",
            "expected_tags": ["example/uat"],
            "group": "help",
            "key": f"case{index}",
            "kind": "seed",
            "label": f"Case {index}",
            "number": index,
        }
        for index in range(1, scenario_count + 1)
    ]
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "manifest_key": "example-config-v1",
        "managed_prefix": "Example ·",
        "technical_namespace": "example_",
        "safety_contract": {
            "activation_strategy": (
                "create_inactive_then_readback_collision_scan_then_activate"
            ),
            "allow_delete": False,
            "allow_existing_object_writes": False,
            "production_group_reference": "forbidden",
        },
        "reference_sets": {
            "H": "all managed ticket-bearing group keys",
            "O": "all managed organization keys",
            "R": "all managed role keys",
            "S": [],
        },
        "groups": groups,
        "organizations": [
            {
                "active": True,
                "class": "customer",
                "domain_assignment": False,
                "key": "organization",
                "name": "Example · Organization",
                "shared": False,
            }
        ],
        "roles": [
            {
                "acl": {"full": ["help"]},
                "key": "support",
                "name": "Example · Support",
            }
        ],
        "users": {
            "agent_constraints": {
                "no_admin": True,
                "no_report_permission": True,
                "notifications": False,
                "one_managed_role_only": True,
            },
            "agents": agents,
            "customer_constraints": {
                "customer_role_only": True,
                "password_login": False,
                "pat": False,
                "saml_identity": False,
            },
            "customers": [
                {"key": "customer", "organization": "organization"}
            ],
            "email_template": "example.{kind}.{key}@example.invalid",
        },
        "overviews": [
            {
                "conditions": {"group": "H", "organization": "O"},
                "key": "open",
                "name": "Example · Open",
                "roles": "R",
            }
        ],
        "macros": [
            {
                "actions": ["add_tag:example/uat"],
                "key": "mark",
                "name": "Example · Mark",
                "scope": "H",
            }
        ],
        "tags": ["example/review", "example/uat"],
        "checklist_templates": [
            {
                "active": False,
                "items": ["Confirm the next step"],
                "key": "intake",
                "name": "Example · Intake",
            }
        ],
        "triggers": [
            {
                "actions": ["add_tag:example/uat"],
                "active": True,
                "conditions": {"all": ["group in H", "organization in O"]},
                "external_effects": False,
                "key": "mark",
                "name": "Example · Trigger mark",
            }
        ],
        "jobs": [
            {
                "actions": ["add_tag:example/review"],
                "active": True,
                "conditions": {"all": ["group in H", "organization in O"]},
                "forbidden_actions": [
                    "ai",
                    "close",
                    "delete",
                    "group_move",
                    "mail",
                    "owner_change",
                    "public_article",
                    "webhook",
                ],
                "key": "review",
                "name": "Example · Review",
                "schedule": "0 7 * * * Europe/Berlin",
            }
        ],
        "report_profiles": [
            {
                "active": True,
                "conditions": {"group": "H", "organization": "O"},
                "key": "volume",
                "name": "Example · Volume",
            }
        ],
        "object_manager": {
            "core_workflows": [
                {
                    "actions": "show core fields",
                    "context": "agent_create",
                    "key": "agent_create_shared",
                    "match": "role in R and group in H",
                }
            ],
            "group_fields": [],
            "organization_fields": [],
            "tenant_default": {
                "default": None,
                "hidden": True,
                "optional": True,
            },
            "ticket_fields": [
                {
                    "name": "example_type",
                    "options": ["a", "b"],
                    "type": "select",
                }
            ],
            "user_fields": [],
        },
        "uat": {
            "article_visibility": "internal",
            "outbound_communication": False,
            "retention": "close_and_retain",
            "ticket_count": scenario_count,
            "title_prefix": "[EXAMPLE]",
        },
    }
    profile: dict[str, Any] = {
        "schema_version": "1.0",
        "profile_key": "example",
        "display_name": "Example",
        "offline_only": True,
        "manifest": "desired-state.json",
        "identity": {
            "agent_firstname": "Example",
            "agent_login_template": "example.agent.{key}",
            "customer_firstname": "Example",
            "customer_login_template": "example.customer.{key}",
            "dummy_only": True,
            "email_template": "example.{kind}.{key}@example.invalid",
            "notifications": False,
        },
        "presentation": {
            "core_workflow_names": {
                "agent_create_shared": "Example · CW · Agent create shared"
            },
            "field_labels": {"example_type": "Type"},
            "object_manager_positions": {
                name: {"start": 1, "step": 1}
                for name in ("Group", "Organization", "Ticket", "User")
            },
            "option_labels": {"a": "A", "b": "B"},
        },
        "uat": {
            "access_matrix": {"seed_keys": ["case1"]},
            "article_visibility": "internal",
            "defaults": {},
            "outbound_communication": False,
            "retention": "close_and_retain",
            "scenarios": scenarios,
            "title_prefix": "[EXAMPLE]",
        },
    }
    return profile, manifest


class QueuewrightTests(unittest.TestCase):
    def write_bundle(
        self, profile: dict[str, Any], manifest: dict[str, Any]
    ) -> Path:
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        (root / "profile.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )
        (root / "desired-state.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        self.addCleanup(directory.cleanup)
        return root

    def assert_invalid(
        self,
        profile: dict[str, Any],
        manifest: dict[str, Any],
        pattern: str,
    ) -> None:
        with self.assertRaisesRegex(ConfigurationError, pattern):
            validate_profile(self.write_bundle(profile, manifest))

    def assert_exact_invalid(
        self,
        profile: dict[str, Any],
        manifest: dict[str, Any],
        expected: str,
    ) -> None:
        with self.assertRaises(ConfigurationError) as raised:
            validate_profile(self.write_bundle(profile, manifest))
        self.assertEqual(str(raised.exception), expected)

    def assert_trace_failure(
        self,
        validation: Any,
        traced_value: Any,
        expected: tuple[str, list[str]],
    ) -> None:
        with self.assertRaises(ConfigurationError) as raised:
            validation()
        expected_error, expected_accesses = expected
        self.assertEqual(str(raised.exception), expected_error)
        self.assertEqual(traced_value.accesses, expected_accesses)

    def test_variable_cardinality_is_derived(self) -> None:
        profile, manifest = fixture_bundle(agent_count=4, scenario_count=6)
        summary = validate_profile(self.write_bundle(profile, manifest))
        self.assertEqual(summary["counts"]["agents"], 4)
        self.assertEqual(summary["counts"]["uat_scenarios"], 6)
        self.assertEqual(summary["counts"]["access_matrix_checks"], 4)

    def test_customer_create_entry_point_workflow_is_compiled(self) -> None:
        profile, manifest = fixture_bundle()
        workflow = {
            "actions": "allow ticket creation only for selected managed services",
            "context": "customer_create",
            "key": "customer_create_entry_points",
            "match": "authenticated customer and group in [help]",
        }
        manifest["object_manager"]["core_workflows"].append(workflow)
        profile["presentation"]["core_workflow_names"][
            "customer_create_entry_points"
        ] = "Example · CW · Customer entry points"

        plan = compile_plan(self.write_bundle(profile, manifest))

        operation = next(
            item
            for item in plan["operations"]
            if item["id"] == "core_workflows:customer_create_entry_points"
        )
        self.assertEqual(operation["desired_state"], workflow)

    def test_university_and_example_inventory_are_data_driven(self) -> None:
        university = validate_profile(ROOT / "studio/templates/university")
        example = validate_profile(ROOT / "profiles/example")
        self.assertEqual(university["counts"]["groups"], 11)
        self.assertEqual(university["counts"]["agents"], 7)
        self.assertEqual(university["counts"]["uat_scenarios"], 8)
        self.assertEqual(university["counts"]["access_matrix_checks"], 49)
        self.assertEqual(university["counts"]["object_manager_fields"], 6)
        self.assertEqual(university["counts"]["jobs"], 1)
        self.assertEqual(example["counts"]["groups"], 2)
        self.assertEqual(example["counts"]["agents"], 1)
        self.assertEqual(example["counts"]["uat_scenarios"], 1)

    def test_plan_is_deterministic_inert_and_dependency_ordered(self) -> None:
        profile, manifest = fixture_bundle()
        root = self.write_bundle(profile, manifest)
        first = compile_plan(root)
        second = compile_plan(root)
        self.assertEqual(first, second)
        self.assertEqual(first["plan_hash"], LEGACY_FIXTURE_PLAN_HASH)
        self.assertFalse(first["safety"]["network_capability"])
        self.assertEqual(set(first["source_hashes"]), {"manifest", "profile"})

        operations = {item["id"]: item for item in first["operations"]}
        self.assertEqual(
            operations["groups:help"]["depends_on"], ["groups:root"]
        )
        self.assertIn(
            "groups:help", operations["roles:support"]["depends_on"]
        )
        self.assertIn(
            "object_manager_fields:example_type",
            operations["core_workflows:agent_create_shared"]["depends_on"],
        )
        self.assertIn(
            "organizations:organization",
            operations["triggers:mark"]["depends_on"],
        )
        self.assertEqual(operations["groups:help"]["action"], "create_inactive")
        self.assertEqual(
            operations["groups:help"]["initial_state"], {"active": False}
        )
        self.assertTrue(
            operations["groups:help"]["desired_state"]["active"]
        )
        self.assertEqual(operations["tags:example/uat"]["action"], "ensure_present")
        sequences = [item["sequence"] for item in first["operations"]]
        self.assertEqual(sequences, list(range(1, len(sequences) + 1)))

    def test_schema_1_1_nested_groups_are_valid_and_dependency_ordered(self) -> None:
        profile, manifest = fixture_bundle()
        profile["schema_version"] = "1.1"
        manifest["schema_version"] = "1.1"
        manifest["groups"].insert(
            1,
            {
                "active": True,
                "key": "faculty",
                "kind": "container",
                "name": "Example · Faculty",
                "parent": "root",
            },
        )
        manifest["groups"][2]["parent"] = "faculty"

        plan = compile_plan(self.write_bundle(profile, manifest))

        operations = {item["id"]: item for item in plan["operations"]}
        self.assertEqual(plan["source_schema_version"], "1.1")
        self.assertEqual(
            operations["groups:faculty"]["depends_on"], ["groups:root"]
        )
        self.assertEqual(
            operations["groups:help"]["depends_on"], ["groups:faculty"]
        )

    def test_schema_1_1_rejects_invalid_group_hierarchies(self) -> None:
        def second_root(manifest: dict[str, Any]) -> None:
            manifest["groups"].insert(
                1,
                {
                    "active": True,
                    "key": "other",
                    "kind": "container",
                    "name": "Example · Other",
                },
            )

        def orphan(manifest: dict[str, Any]) -> None:
            manifest["groups"][1]["parent"] = "missing"

        def cycle(manifest: dict[str, Any]) -> None:
            manifest["groups"].insert(
                1,
                {
                    "active": True,
                    "key": "branch",
                    "kind": "container",
                    "name": "Example · Branch",
                    "parent": "branch_two",
                },
            )
            manifest["groups"].insert(
                2,
                {
                    "active": True,
                    "key": "branch_two",
                    "kind": "container",
                    "name": "Example · Branch two",
                    "parent": "branch",
                },
            )

        cases = (
            ("second root", second_root, "exactly one root"),
            ("orphan", orphan, "group parent invalid"),
            ("cycle", cycle, "contains a cycle"),
        )
        for label, mutate, pattern in cases:
            with self.subTest(label=label):
                profile, manifest = fixture_bundle()
                profile["schema_version"] = "1.1"
                manifest["schema_version"] = "1.1"
                mutate(manifest)
                self.assert_invalid(profile, manifest, pattern)

    def test_schema_1_0_still_rejects_nested_containers(self) -> None:
        profile, manifest = fixture_bundle()
        manifest["groups"][0]["parent"] = "root"
        self.assert_invalid(profile, manifest, "unsupported field: parent")

    def test_compile_and_cli_use_one_loaded_snapshot(self) -> None:
        profile, manifest = fixture_bundle()
        root = self.write_bundle(profile, manifest)
        with mock.patch(
            "queuewright.compiler.load_profile",
            wraps=load_profile,
        ) as compiler_loader:
            compile_plan(root)
        compiler_loader.assert_called_once_with(root)

        original_validate = compiler_module.validate_loaded_profile

        def mutate_file_after_validation(
            loaded: dict[str, Any],
        ) -> dict[str, Any]:
            summary = original_validate(loaded)
            changed = json.loads(
                (root / "desired-state.json").read_text(encoding="utf-8")
            )
            changed["groups"][0]["credential"] = "unvalidated"
            (root / "desired-state.json").write_text(
                json.dumps(changed), encoding="utf-8"
            )
            return summary

        with mock.patch(
            "queuewright.compiler.validate_loaded_profile",
            side_effect=mutate_file_after_validation,
        ):
            plan = compile_plan(root)
        root_group = next(
            operation
            for operation in plan["operations"]
            if operation["id"] == "groups:root"
        )
        self.assertNotIn("credential", root_group["desired_state"])

        (root / "desired-state.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        stdout = io.StringIO()
        with mock.patch(
            "queuewright.cli.load_profile",
            wraps=load_profile,
        ) as cli_loader, contextlib.redirect_stdout(stdout):
            self.assertEqual(main(["validate", str(root)]), 0)
        cli_loader.assert_called_once_with(str(root))

    def test_safety_rejections(self) -> None:
        profile, manifest = fixture_bundle()
        manifest["safety_contract"]["allow_delete"] = True
        self.assert_invalid(profile, manifest, "safety contract")

        profile, manifest = fixture_bundle()
        manifest["roles"][0]["acl"]["full"] = ["root"]
        self.assert_invalid(profile, manifest, "unknown key")

        profile, manifest = fixture_bundle()
        manifest["organizations"][0]["shared"] = True
        self.assert_invalid(profile, manifest, "unshared")

        profile, manifest = fixture_bundle()
        manifest["triggers"][0]["external_effects"] = True
        self.assert_invalid(profile, manifest, "external effects")

        profile, manifest = fixture_bundle()
        manifest["triggers"][0]["actions"] = ["add_tag:example/missing"]
        self.assert_invalid(profile, manifest, "undeclared")

        profile, manifest = fixture_bundle()
        manifest["triggers"][0]["actions"] = ["add_tag"]
        self.assert_invalid(profile, manifest, "requires an argument")

        profile, manifest = fixture_bundle()
        manifest["triggers"][0]["actions"] = [" ADD_TAG:example/uat "]
        self.assert_invalid(profile, manifest, "canonical spelling")

        profile, manifest = fixture_bundle()
        manifest["macros"][0]["actions"] = ["run_command"]
        self.assert_invalid(profile, manifest, "unsupported action")

        profile, manifest = fixture_bundle()
        manifest["triggers"][0]["conditions"]["all"][0] = "not group in H"
        self.assert_invalid(profile, manifest, "lacks required")

        profile, manifest = fixture_bundle()
        manifest["jobs"][0]["forbidden_actions"].remove("close")
        self.assert_invalid(profile, manifest, "forbidden actions")

        profile, manifest = fixture_bundle()
        profile["presentation"]["field_labels"] = {}
        self.assert_invalid(profile, manifest, "field labels")

        profile, manifest = fixture_bundle()
        profile["uat"]["scenarios"][0]["group"] = "production"
        self.assert_invalid(profile, manifest, "invalid UAT scenario")

        profile, manifest = fixture_bundle()
        profile["identity"]["agent_login_template"] = "agent.{key}"
        self.assert_invalid(profile, manifest, "profile-namespaced")

        profile, manifest = fixture_bundle()
        manifest["reference_sets"]["H"] = "anything"
        self.assert_invalid(profile, manifest, "reference set descriptors")

        profile, manifest = fixture_bundle()
        manifest["groups"][0]["credential"] = "must-not-pass"
        self.assert_invalid(profile, manifest, "unsupported field: credential")

        profile, manifest = fixture_bundle()
        profile["display_name"] = "https://tenant.invalid"
        self.assert_invalid(profile, manifest, "must not contain a URL")

        profile, manifest = fixture_bundle()
        manifest["reference_sets"]["S"] = [{}]
        self.assert_invalid(profile, manifest, "reference set descriptors")

        profile, manifest = fixture_bundle()
        profile["uat"]["scenarios"][0]["expected_tags"] = [{}]
        self.assert_invalid(profile, manifest, "invalid UAT scenario tags")

        profile, manifest = fixture_bundle()
        profile["uat"]["access_matrix"]["seed_keys"] = [{}]
        self.assert_invalid(profile, manifest, "UAT seed coverage")

        profile, manifest = fixture_bundle()
        profile["uat"]["defaults"] = {"type": {}}
        self.assert_invalid(profile, manifest, "UAT default for type")

        profile, manifest = fixture_bundle()
        profile["uat"]["scenarios"][0]["type"] = {}
        self.assert_invalid(profile, manifest, "invalid UAT option override type")

    def test_job_automation_contract_rejects_each_invalid_operand(self) -> None:
        required_actions = [
            "ai",
            "close",
            "delete",
            "group_move",
            "mail",
            "owner_change",
            "public_article",
            "webhook",
        ]

        def missing_forbidden_actions(job: dict[str, Any]) -> None:
            del job["forbidden_actions"]

        def non_list_forbidden_actions(job: dict[str, Any]) -> None:
            job["forbidden_actions"] = {"actions": required_actions}

        def non_string_forbidden_action(job: dict[str, Any]) -> None:
            job["forbidden_actions"] = [*required_actions[:-1], 1]

        def incomplete_forbidden_actions(job: dict[str, Any]) -> None:
            job["forbidden_actions"] = required_actions[:-1]

        def missing_schedule(job: dict[str, Any]) -> None:
            del job["schedule"]

        def non_string_schedule(job: dict[str, Any]) -> None:
            job["schedule"] = 7

        def empty_schedule(job: dict[str, Any]) -> None:
            job["schedule"] = ""

        cases = (
            (
                "missing forbidden actions",
                missing_forbidden_actions,
                "job review misses required field: forbidden_actions",
            ),
            (
                "non-list forbidden actions",
                non_list_forbidden_actions,
                "job review must declare schedule and all forbidden actions",
            ),
            (
                "non-string forbidden action",
                non_string_forbidden_action,
                "job review must declare schedule and all forbidden actions",
            ),
            (
                "incomplete forbidden actions",
                incomplete_forbidden_actions,
                "job review must declare schedule and all forbidden actions",
            ),
            (
                "missing schedule",
                missing_schedule,
                "job review misses required field: schedule",
            ),
            (
                "non-string schedule",
                non_string_schedule,
                "job review must declare schedule and all forbidden actions",
            ),
            (
                "empty schedule",
                empty_schedule,
                "job review must declare schedule and all forbidden actions",
            ),
        )
        for label, mutate, expected in cases:
            with self.subTest(label=label):
                profile, manifest = fixture_bundle()
                mutate(manifest["jobs"][0])
                self.assert_exact_invalid(profile, manifest, expected)

        profile, manifest = fixture_bundle()
        manifest["jobs"][0]["schedule"] = " "
        self.assertEqual(validate_profile(self.write_bundle(profile, manifest))["counts"]["jobs"], 1)

    def test_object_field_options_reject_each_invalid_operand(self) -> None:
        def missing_options(field: dict[str, Any]) -> None:
            del field["options"]

        def non_list_options(field: dict[str, Any]) -> None:
            field["options"] = {"options": ["a", "b"]}

        def empty_options(field: dict[str, Any]) -> None:
            field["options"] = []

        def non_string_option(field: dict[str, Any]) -> None:
            field["options"] = ["a", 1]

        def empty_string_option(field: dict[str, Any]) -> None:
            field["options"] = ["a", ""]

        def duplicate_option(field: dict[str, Any]) -> None:
            field["options"] = ["a", "a"]

        cases = (
            (
                "missing options",
                missing_options,
                "object_manager.ticket_fields field misses required field: options",
            ),
            (
                "non-list options",
                non_list_options,
                "object manager options must be unique strings: example_type",
            ),
            (
                "empty options",
                empty_options,
                "object manager options must be unique strings: example_type",
            ),
            (
                "non-string option",
                non_string_option,
                "object manager options must be unique strings: example_type",
            ),
            (
                "empty string option",
                empty_string_option,
                "object manager options must be unique strings: example_type",
            ),
            (
                "duplicate option",
                duplicate_option,
                "object manager options must be unique strings: example_type",
            ),
        )
        for label, mutate, expected in cases:
            with self.subTest(label=label):
                profile, manifest = fixture_bundle()
                mutate(manifest["object_manager"]["ticket_fields"][0])
                self.assert_exact_invalid(profile, manifest, expected)

        profile, manifest = fixture_bundle()
        manifest["object_manager"]["ticket_fields"][0]["options"] = [" "]
        profile["presentation"]["option_labels"] = {" ": "Space"}
        self.assertEqual(
            validate_profile(self.write_bundle(profile, manifest))["counts"]["object_manager_fields"],
            1,
        )

    def _assert_core_workflow_missing_fields(self) -> None:
        for field in _CORE_WORKFLOW_MISSING_FIELDS:
            with self.subTest(field=field):
                profile, manifest = fixture_bundle()
                del manifest["object_manager"]["core_workflows"][0][field]
                self.assert_exact_invalid(
                    profile,
                    manifest,
                    f"core workflow agent_create_shared misses required field: {field}",
                )

    def _assert_core_workflow_invalid_values(self) -> None:
        for label, field, value in _CORE_WORKFLOW_INVALID_VALUES:
            with self.subTest(label=label):
                profile, manifest = fixture_bundle()
                manifest["object_manager"]["core_workflows"][0][field] = value
                self.assert_exact_invalid(profile, manifest, _CORE_WORKFLOW_CONTRACT_ERROR)

    def _assert_core_workflow_accepted_text(self) -> None:
        for context in ("agent_edit", "customer_create"):
            with self.subTest(context=context):
                profile, manifest = fixture_bundle()
                workflow = manifest["object_manager"]["core_workflows"][0]
                workflow["context"] = context
                workflow["match"] = " "
                workflow["actions"] = " "
                self.assertEqual(
                    validate_profile(self.write_bundle(profile, manifest))["counts"]["core_workflows"],
                    1,
                )

    def test_core_workflow_contract_rejects_each_invalid_operand(self) -> None:
        self._assert_core_workflow_missing_fields()
        self._assert_core_workflow_invalid_values()
        self._assert_core_workflow_accepted_text()

    def test_job_automation_checks_forbidden_actions_before_schedule(self) -> None:
        class TrackingJob(dict[str, Any]):
            def __init__(self, value: dict[str, Any]) -> None:
                super().__init__(value)
                self.accesses: list[str] = []

            def get(self, key: str, default: Any = None) -> Any:
                self.accesses.append(key)
                return super().get(key, default)

        job = TrackingJob({"forbidden_actions": ["ai"], "schedule": 7})
        self.assert_trace_failure(
            lambda: profile_automation._validate_job_automation(job, "review"),
            job,
            (
                "job review must declare schedule and all forbidden actions",
                ["forbidden_actions"],
            ),
        )

    def test_core_workflow_checks_context_match_and_actions_in_order(self) -> None:
        class TrackingWorkflow(dict[str, Any]):
            def __init__(self, value: dict[str, Any]) -> None:
                super().__init__(value)
                self.accesses: list[str] = []

            def get(self, key: str, default: Any = None) -> Any:
                self.accesses.append(key)
                return super().get(key, default)

        cases = (
            (
                "context",
                {
                    "actions": None,
                    "context": "agent_delete",
                    "key": "workflow",
                    "match": None,
                },
                ["key", "context"],
            ),
            (
                "match",
                {
                    "actions": None,
                    "context": "agent_create",
                    "key": "workflow",
                    "match": None,
                },
                ["key", "context", "match"],
            ),
            (
                "actions",
                {
                    "actions": None,
                    "context": "agent_create",
                    "key": "workflow",
                    "match": "match",
                },
                ["key", "context", "match", "actions"],
            ),
        )
        for label, value, expected_accesses in cases:
            with self.subTest(label=label):
                workflow = TrackingWorkflow(value)
                self.assert_trace_failure(
                    lambda: profile_automation._validate_core_workflows(
                        {"core_workflows": [workflow]}
                    ),
                    workflow,
                    (
                        "core workflow workflow has an invalid declarative contract",
                        expected_accesses,
                    ),
                )

    def test_profile_path_and_output_are_protected(self) -> None:
        profile, manifest = fixture_bundle()
        root = self.write_bundle(profile, manifest)
        profile["manifest"] = "../outside.json"
        (root / "profile.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )
        with self.assertRaisesRegex(ConfigurationError, "escapes"):
            validate_profile(root)

        profile, manifest = fixture_bundle()
        root = self.write_bundle(profile, manifest)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(
                [
                    "plan",
                    str(root),
                    "--output",
                    str(root / "profile.json"),
                ]
            )
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(
                [
                    "plan",
                    str(root),
                    "--output",
                    str(root / ".env.plan.json"),
                ]
            )

        output = root / "compiled-plan.json"
        self.assertEqual(main(["plan", str(root), "--output", str(output)]), 0)
        self.assertEqual(json.loads(output.read_text())["profile_key"], "example")

        original = output.read_text(encoding="utf-8")
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(["plan", str(root), "--output", str(output)])
        self.assertEqual(output.read_text(encoding="utf-8"), original)

        failed_output = root / "failed-plan.json"
        with mock.patch.object(
            Path,
            "hardlink_to",
            side_effect=OSError("simulated publish failure"),
        ), contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(["plan", str(root), "--output", str(failed_output)])
        self.assertFalse(failed_output.exists())
        self.assertEqual(list(root.glob(".queuewright-*")), [])

    def test_package_has_no_network_or_environment_surface(self) -> None:
        allowed_imports = {
            "__future__",
            "argparse",
            "copy",
            "hashlib",
            "json",
            "pathlib",
            "re",
            "tempfile",
            "typing",
        }

        def import_roots(tree: ast.AST) -> set[str]:
            roots: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    roots.add((node.module or "").split(".", 1)[0])
            return roots

        probe = ast.parse("from urllib.request import urlopen")
        self.assertEqual(import_roots(probe), {"urllib"})
        self.assertFalse(import_roots(probe).issubset(allowed_imports))

        def dynamic_import_markers(tree: ast.AST) -> list[ast.AST]:
            return [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Name)
                and node.id in {"__import__", "compile", "eval", "exec"}
                or isinstance(node, ast.Attribute)
                and node.attr == "import_module"
            ]

        alias_probe = ast.parse('loader = __import__\nloader("socket")')
        self.assertTrue(dynamic_import_markers(alias_probe))

        for path in (ROOT / "queuewright").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            self.assertTrue(import_roots(tree).issubset(allowed_imports), path)
            self.assertFalse(dynamic_import_markers(tree), path)


if __name__ == "__main__":
    unittest.main()
