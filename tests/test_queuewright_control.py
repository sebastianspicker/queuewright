"""Durable, fail-closed connected-control contracts."""

from __future__ import annotations

import os
import tempfile
import unittest

from queuewright_control import AdapterPolicy, ControlError, ControlPlane, InMemoryKeyProvider, Ledger, Operation
from tests.control_test_support import FakeTransport, FlakyAnchorProvider


class ControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.ledger = Ledger(os.path.join(self.directory.name, "ledger.sqlite3"), InMemoryKeyProvider(b"k" * 32))
        self.transport = FakeTransport()
        self.policy = AdapterPolicy("v1", {"groups": ("POST", "PATCH")},
                                    body_fields={"groups": ("name", "active", "roles")},
                                    required_permissions={"groups": ("admin.group",)})
        self.plane = ControlPlane(self.ledger, self.policy, self.transport,
                                  resolver=lambda _: ["93.184.216.34"])
        self.operation = Operation("create-group", "POST", "groups", "managed-group",
                                   {"name": "Managed Group", "active": False}, "low", "absent",
                                   "created-hash", rollback={"created": True, "postcondition": "inactive-hash"},
                                   required_permissions=("admin.group",))

    def tearDown(self) -> None:
        self.plane.disconnect()
        self.ledger.close()
        self.directory.cleanup()

    def ready(self) -> None:
        self.plane.connect("https://tenant.example", "very-secret-token")
        preview = self.plane.make_preview({"version": 1}, {"graph": 1}, [self.operation], project_id="project-one")
        self.plane.approve(preview.hash)

    def test_identity_and_credential_boundary(self) -> None:
        with self.assertRaises(ControlError):
            self.plane.connect("http://tenant.example", "secret")
        with self.assertRaises(ControlError):
            self.plane.connect("https://tenant.example", "token with space")
        connection = self.plane.connect("HTTPS://Tenant.Example./", "secret")
        self.assertEqual(connection.origin, "https://tenant.example")
        self.plane.disconnect()
        invalid = FakeTransport()
        invalid.identity["actor"] = ""
        plane = ControlPlane(self.ledger, self.policy, invalid, resolver=lambda _: ["93.184.216.34"])
        with self.assertRaisesRegex(ControlError, "claims are incomplete"):
            plane.connect("https://tenant.example", "temporary-secret")
        self.assertTrue(invalid.calls[0][1]["credential"].closed)  # type: ignore[union-attr]

    def test_preview_is_immutable_one_use_and_policy_bound(self) -> None:
        nested = Operation("nested", "POST", "groups", "target", {"roles": [{"name": "reader"}]},
                           "low", "absent", "nested-hash", rollback={"created": True},
                           required_permissions=("admin.group",))
        self.plane.connect("https://tenant.example", "secret")
        preview = self.plane.make_preview({}, {}, [nested], project_id="project-one")
        self.plane.approve(preview.hash)
        with self.assertRaises(TypeError):
            nested.body["roles"][0]["name"] = "administrator"  # type: ignore[index]
        self.plane.apply("run-one", {}, {})
        with self.assertRaisesRegex(ControlError, "approval"):
            self.plane.apply("run-two", {}, {})
        self.plane.disconnect()

    def test_ambiguous_write_reconciles_and_verifies(self) -> None:
        self.transport.ambiguous = True
        self.ready()
        self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.assertIn("reconcile", [kind for kind, _ in self.transport.calls])
        self.plane.verify("run-one")
        self.assertEqual(self.ledger.state("run-one"), "verified")

    def test_auth_bound_durable_resume(self) -> None:
        self.transport.bad_readback = True
        self.ready()
        with self.assertRaises(ControlError):
            self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.plane.disconnect()
        resumed = ControlPlane(self.ledger, self.policy, FakeTransport(), resolver=lambda _: ["93.184.216.34"])
        resumed.connect("https://tenant.example", "replacement-token")
        resumed.resume_run("run-one")
        resumed.reconcile("run-one")
        resumed.rollback("run-one")
        self.assertEqual(self.ledger.state("run-one"), "rolled_back")
        resumed.disconnect()

    def test_rollback_recovers_after_response_loss(self) -> None:
        self.ready()
        self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.transport.rollback_applied_then_raises = True
        with self.assertRaisesRegex(ControlError, "ambiguous"):
            self.plane.rollback("run-one")
        self.plane.rollback("run-one")
        self.assertEqual(self.ledger.state("run-one"), "rolled_back")

    def test_authenticated_tamper_fails_closed(self) -> None:
        self.ready()
        self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.ledger.db.execute("UPDATE runs SET state='verified' WHERE run_id='run-one'")
        with self.assertRaisesRegex(ControlError, "authenticated audit"):
            self.plane.rollback("run-one")
        self.assertNotIn("rollback", [kind for kind, _ in self.transport.calls])

    def test_anchor_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "recoverable.sqlite3")
            provider = FlakyAnchorProvider(b"a" * 32)
            ledger = Ledger(path, provider)
            provider.fail_updates = 1
            with self.assertRaisesRegex(ControlError, "anchor could not be advanced"):
                ledger.audit("run", "event", {"safe": True})
            ledger.close()
            reopened = Ledger(path, provider)
            self.assertTrue(reopened.verify_audit_chain())
            reopened.close()
