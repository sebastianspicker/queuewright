"""Characterization tests for the public profile-validation facade."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from queuewright.cli import main
from queuewright.configuration import validate_loaded_profile
from queuewright.errors import ConfigurationError

ROOT = Path(__file__).resolve().parents[1]


def example_loaded() -> dict[str, object]:
    root = ROOT / "queuewright" / "examples" / "minimal"
    return {
        "profile": json.loads((root / "profile.json").read_text(encoding="utf-8")),
        "manifest": json.loads((root / "desired-state.json").read_text(encoding="utf-8")),
    }


class ProfileValidationTests(unittest.TestCase):
    def test_validation_keeps_fail_closed_messages_for_contract_boundaries(self) -> None:
        cases = (
            (
                "offline-only",
                lambda loaded: loaded["profile"].__setitem__("offline_only", False),
                "profile requires display_name and offline_only true",
            ),
            (
                "namespace",
                lambda loaded: loaded["manifest"].__setitem__("technical_namespace", "bad"),
                "invalid managed prefix or technical namespace",
            ),
            (
                "safety",
                lambda loaded: loaded["manifest"]["safety_contract"].__setitem__("allow_delete", True),
                "invalid safety contract",
            ),
            (
                "tags",
                lambda loaded: loaded["manifest"].__setitem__("tags", ["outside/managed"]),
                "tags must be unique and namespaced",
            ),
        )
        for name, mutate, message in cases:
            with self.subTest(name=name):
                loaded = copy.deepcopy(example_loaded())
                mutate(loaded)
                with self.assertRaisesRegex(ConfigurationError, message):
                    validate_loaded_profile(loaded)  # type: ignore[arg-type]


def set_role_to_list(loaded: dict[str, object]) -> None:
    loaded["manifest"]["users"]["agents"][0]["role"] = []


def set_group_kind_to_object(loaded: dict[str, object]) -> None:
    loaded["manifest"]["groups"][1]["kind"] = {}


def set_customer_organization_to_list(loaded: dict[str, object]) -> None:
    loaded["manifest"]["users"]["customers"][0]["organization"] = []


class ValidationTotalityTests(unittest.TestCase):
    def test_wrongly_shaped_values_raise_configuration_error(self) -> None:
        for mutate in (
            set_role_to_list,
            set_group_kind_to_object,
            set_customer_organization_to_list,
        ):
            with self.subTest(mutation=mutate.__name__):
                loaded = example_loaded()
                mutate(loaded)
                with self.assertRaises(ConfigurationError):
                    validate_loaded_profile(loaded)

    def test_cli_reports_wrongly_shaped_bundle_as_usage_error(self) -> None:
        loaded = example_loaded()
        set_role_to_list(loaded)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "desired-state.json").write_text(
                json.dumps(loaded["manifest"]), encoding="utf-8"
            )
            (target / "profile.json").write_text(json.dumps(loaded["profile"]), encoding="utf-8")
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                main(["validate", str(target / "profile.json")])
        self.assertEqual(raised.exception.code, 2)
