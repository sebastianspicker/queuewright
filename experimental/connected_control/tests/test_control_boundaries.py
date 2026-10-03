"""Focused fail-closed boundary tests for the experimental control package."""

from __future__ import annotations

import math
import os
import tempfile
import unittest
from unittest.mock import patch

from control_test_support import FakeTransport
from queuewright_control import (
    AdapterPolicy,
    CapabilityDiscovery,
    ControlError,
    ControlPlane,
    InMemoryKeyProvider,
    Ledger,
    Operation,
)
from queuewright_control.model_credentials import (
    EphemeralCredential,
    MacOSKeychainProvider,
)
from queuewright_control.model_protocol import (
    _canonical_origin,
    _freeze,
    _strict_json,
    _validate_addresses,
)


class CapabilityDiscoveryBoundaryTests(unittest.TestCase):
    def test_pagination_completes_only_on_a_short_page(self) -> None:
        pages = {
            1: (200, ({"id": "one"}, {"id": "two"})),
            2: (206, ({"id": "three"},)),
        }

        result = CapabilityDiscovery.pages(
            lambda page: pages[page], max_pages=3, page_size=2
        )

        self.assertEqual(result.support, "supported")
        self.assertEqual(result.delivery, "automated")
        self.assertTrue(result.complete)
        self.assertEqual([item["id"] for item in result.items], ["one", "two", "three"])
        with self.assertRaises(TypeError):
            result.items[0]["id"] = "changed"  # type: ignore[index]

    def test_page_bound_and_repeated_page_never_claim_completeness(self) -> None:
        bounded = CapabilityDiscovery.pages(
            lambda page: (200, ({"page": page},)), max_pages=2, page_size=1
        )
        self.assertEqual((bounded.support, bounded.delivery, bounded.complete),
                         ("supported", "verify_only", False))
        self.assertEqual(len(bounded.items), 2)

        repeated = CapabilityDiscovery.pages(
            lambda _page: (200, ({"id": "same"},)), max_pages=4, page_size=1
        )
        self.assertEqual((repeated.delivery, repeated.complete), ("verify_only", False))
        self.assertEqual(len(repeated.items), 1)

    def test_status_and_malformed_page_results_are_distinct(self) -> None:
        cases = (
            (403, "permission_blocked"),
            (404, "unknown"),
            (500, "unknown"),
        )
        for status, expected_support in cases:
            with self.subTest(status=status):
                result = CapabilityDiscovery.pages(
                    lambda _page, status=status: (status, ()), max_pages=1
                )
                self.assertEqual(result.support, expected_support)
                self.assertFalse(result.complete)

        malformed = CapabilityDiscovery.pages(
            lambda page: (200, ({"id": "safe"},) if page == 1 else ({"api_token": "x"},)),
            max_pages=3,
            page_size=1,
        )
        self.assertEqual((malformed.support, malformed.delivery, malformed.complete),
                         ("unknown", "unsupported", False))
        self.assertEqual([item["id"] for item in malformed.items], ["safe"])


class ProtocolBoundaryTests(unittest.TestCase):
    def test_origins_are_canonical_and_credential_free(self) -> None:
        self.assertEqual(
            _canonical_origin("HTTPS://BÜCHER.Example.:443/"),
            ("https://xn--bcher-kva.example:443", "xn--bcher-kva.example"),
        )
        self.assertEqual(
            _canonical_origin("https://[2001:0db8::1]:8443"),
            ("https://[2001:db8::1]:8443", "2001:db8::1"),
        )
        invalid = (
            "http://tenant.example",
            "https://user@tenant.example",
            "https://tenant.example/path",
            "https://tenant.example?query=yes",
            "https://tenant.example:0",
            "https://tenant.example:99999",
            "https://999.999.999.999",
        )
        for origin in invalid:
            with self.subTest(origin=origin), self.assertRaises(ControlError):
                _canonical_origin(origin)

    def test_address_pinning_normalizes_and_enforces_origin_policy(self) -> None:
        self.assertEqual(
            _validate_addresses(
                "tenant.example", ["2606:2800:220:1:248:1893:25c8:1946", "93.184.216.34", "93.184.216.34"], False
            ),
            ("2606:2800:220:1:248:1893:25c8:1946", "93.184.216.34"),
        )
        self.assertEqual(
            _validate_addresses("127.0.0.1", ["127.0.0.1"], True),
            ("127.0.0.1",),
        )
        for host, addresses, allow_private, code in (
            ("tenant.example", [], False, "identity_invalid"),
            ("tenant.example", ["127.0.0.1"], False, "origin_forbidden"),
            ("192.0.2.10", ["192.0.2.11"], True, "identity_invalid"),
            ("tenant.example", [7], True, "identity_invalid"),
        ):
            with self.subTest(host=host, addresses=addresses):
                with self.assertRaises(ControlError) as raised:
                    _validate_addresses(host, addresses, allow_private)
                self.assertEqual(raised.exception.code, code)

    def test_json_validation_rejects_sensitive_or_non_json_values_and_freezes(self) -> None:
        frozen = _freeze({"items": [{"enabled": True}], "count": 2})
        self.assertEqual(frozen["items"][0]["enabled"], True)
        with self.assertRaises(TypeError):
            frozen["count"] = 3  # type: ignore[index]
        for value, expected_code in (
            ({"apiKey": "fictional"}, "sensitive_input"),
            ({1: "value"}, "invalid_json"),
            ({"value": math.nan}, "invalid_json"),
            ({"value": object()}, "invalid_json"),
        ):
            with self.subTest(value=value):
                with self.assertRaises(ControlError) as raised:
                    _strict_json(value)
                self.assertEqual(raised.exception.code, expected_code)


class CredentialAndKeyBoundaryTests(unittest.TestCase):
    def test_ephemeral_credential_expires_redacts_and_zeroes_on_close(self) -> None:
        with patch("queuewright_control.model_credentials.time.time", return_value=100.0):
            credential = EphemeralCredential("fictional-token", 110.0)
            self.assertEqual(credential.reveal(), "fictional-token")
            self.assertNotIn("fictional-token", repr(credential))

        credential.close()
        credential.close()
        self.assertTrue(credential.closed)
        self.assertEqual(bytes(credential._value), b"\0" * len("fictional-token"))
        with self.assertRaises(ControlError) as raised:
            credential.reveal()
        self.assertEqual(raised.exception.code, "credential_expired")

        with (
            patch("queuewright_control.model_credentials.time.time", return_value=111.0),
            self.assertRaises(ControlError),
        ):
            EphemeralCredential("fictional-token", 110.0)
        for invalid in ("", "two words", "line\nbreak"):
            with self.subTest(invalid=invalid), self.assertRaises(ControlError):
                EphemeralCredential(invalid, 10**12)

    def test_key_providers_fail_closed_and_compare_and_set(self) -> None:
        unavailable = MacOSKeychainProvider()
        for call, expected_path in (
            (unavailable.get_key, "/ledger/key"),
            (unavailable.get_audit_anchor, "/ledger/audit-anchor"),
            (lambda: unavailable.compare_and_set_audit_anchor(None, (1, "head")), "/ledger/audit-anchor"),
        ):
            with self.subTest(path=expected_path):
                with self.assertRaises(ControlError) as raised:
                    call()
                self.assertEqual((raised.exception.code, raised.exception.path),
                                 ("key_unavailable", expected_path))

        provider = InMemoryKeyProvider(b"k" * 32)
        self.assertTrue(provider.compare_and_set_audit_anchor(None, (1, "first")))
        self.assertFalse(provider.compare_and_set_audit_anchor(None, (2, "stale")))
        self.assertEqual(provider.get_audit_anchor(), (1, "first"))
        self.assertTrue(provider.compare_and_set_audit_anchor((1, "first"), (2, "next")))
        self.assertEqual(provider.get_audit_anchor(), (2, "next"))


class LedgerBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.ledger = Ledger(
            os.path.join(self.directory.name, "boundaries.sqlite3"),
            InMemoryKeyProvider(b"b" * 32),
        )

    def tearDown(self) -> None:
        self.ledger.close()
        self.directory.cleanup()

    def test_lock_expiry_renewal_reacquisition_release_and_conflicts(self) -> None:
        with patch("queuewright_control.ledger_locks.time.time", return_value=100.0):
            first_fence = self.ledger.acquire_lock("project", "run-one", "preview-one", 10)
        with patch("queuewright_control.ledger_locks.time.time", return_value=105.0):
            self.assertEqual(
                self.ledger.renew_lock("project", "run-one", "preview-one", 10),
                first_fence,
            )
            with self.assertRaisesRegex(ControlError, "competing live lease"):
                self.ledger.ensure_lock("project", "run-two", "preview-two", 10)
        with patch("queuewright_control.ledger_locks.time.time", return_value=116.0):
            with self.assertRaisesRegex(ControlError, "no longer owns"):
                self.ledger.assert_lock("project", "run-one", "preview-one")
            second_fence = self.ledger.ensure_lock("project", "run-one", "preview-one", 10)
        self.assertNotEqual(first_fence, second_fence)
        with self.assertRaisesRegex(ControlError, "ownership does not match"):
            self.ledger.release_lock("project", "run-one", "wrong-preview")
        self.ledger.release_lock("project", "run-one", "preview-one")
        with self.assertRaises(ControlError):
            self.ledger.assert_lock("project", "run-one", "preview-one")

    def test_incomplete_run_blocks_new_lock_even_after_lease_expiry(self) -> None:
        self.ledger.begin_run("run-one", "preview-one", "tenant", "project")
        with patch("queuewright_control.ledger_locks.time.time", return_value=100.0):
            self.ledger.acquire_lock("project", "run-one", "preview-one", 1)
        with (
            patch("queuewright_control.ledger_locks.time.time", return_value=200.0),
            self.assertRaises(ControlError) as raised,
        ):
            self.ledger.acquire_lock("project", "run-two", "preview-two", 10)
        self.assertEqual(raised.exception.code, "run_recovery_required")
        self.assertEqual(raised.exception.run_id, "run-one")

    def test_retention_keeps_incomplete_preview_then_purges_terminal_evidence(self) -> None:
        with patch("queuewright_control.ledger_runs.time.time", return_value=10.0):
            self.ledger.put_blob("old-generic", b"generic")
            self.ledger.put_blob("preview:active", b"active")
            self.ledger.begin_run("active-run", "active", "tenant", "project")

        self.assertEqual(self.ledger.purge_evidence(before=100.0), 1)
        self.assertIsNone(self.ledger.get_blob("old-generic"))
        self.assertEqual(self.ledger.get_blob("preview:active"), b"active")

        self.ledger.set_state("active-run", "verified")
        self.assertEqual(self.ledger.purge_evidence(before=100.0), 1)
        self.assertIsNone(self.ledger.get_blob("preview:active"))


class RecoveryDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.ledger = Ledger(
            os.path.join(self.directory.name, "recovery.sqlite3"),
            InMemoryKeyProvider(b"r" * 32),
        )
        self.transport = FakeTransport()
        self.policy = AdapterPolicy(
            "v1",
            {"groups": ("POST",)},
            body_fields={"groups": ("name", "active")},
            required_permissions={"groups": ("admin.group",)},
        )
        self.plane = ControlPlane(
            self.ledger,
            self.policy,
            self.transport,
            resolver=lambda _host: ["93.184.216.34"],
        )
        self.operation = Operation(
            "create-group",
            "POST",
            "groups",
            "managed-group",
            {"name": "Fictional Managed Group", "active": False},
            "low",
            "absent",
            "created-hash",
            rollback={"created": True, "postcondition": "inactive-hash"},
            required_permissions=("admin.group",),
        )
        self.plane.connect("https://tenant.example", "fictional-session-token")
        preview = self.plane.make_preview(
            {"version": 1}, {"graph": 1}, [self.operation], project_id="project-one"
        )
        self.plane.approve(preview.hash)

    def tearDown(self) -> None:
        self.plane.disconnect()
        self.ledger.close()
        self.directory.cleanup()

    def _leave_ambiguous_intent(self) -> None:
        self.transport.ambiguous = True
        self.transport.reconcile_not_applied = True
        with self.assertRaises(ControlError) as raised:
            self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.assertEqual(raised.exception.code, "outcome_ambiguous")
        self.assertEqual(self.ledger.state("run-one"), "outcome_ambiguous")

    def test_reconcile_can_prove_not_applied_without_claiming_success(self) -> None:
        self._leave_ambiguous_intent()
        self.plane.reconcile("run-one")
        self.assertEqual(self.ledger.not_applied("run-one"), {"create-group"})
        self.assertEqual(self.ledger.state("run-one"), "partially_applied")

    def test_unprovable_reconciliation_requires_manual_recovery(self) -> None:
        self._leave_ambiguous_intent()
        self.transport.reconcile_not_applied = False

        original = self.transport._reconciliation_response
        self.transport._reconciliation_response = lambda _operation: {  # type: ignore[method-assign]
            "matched": False,
            "hash": "unrelated-state",
        }
        self.addCleanup(setattr, self.transport, "_reconciliation_response", original)
        with self.assertRaises(ControlError) as raised:
            self.plane.reconcile("run-one")
        self.assertEqual(raised.exception.code, "manual_recovery")
        self.assertEqual(self.ledger.state("run-one"), "manual_recovery")
        self.assertEqual(self.plane.session_state, "manual_recovery")


if __name__ == "__main__":
    unittest.main()
