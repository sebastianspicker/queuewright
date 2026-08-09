"""Fail-closed tests for the transport-injected connected-mode foundation."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest

from queuewright_control import (
    AdapterPolicy,
    CapabilityDiscovery,
    ControlError,
    ControlPlane,
    InMemoryKeyProvider,
    Ledger,
    Operation,
)
from tests.control_test_support import FakeTransport, FlakyAnchorProvider


class ControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "ledger.sqlite3")
        self.ledger = Ledger(self.path, InMemoryKeyProvider(b"k" * 32))
        self.transport = FakeTransport()
        self.policy = AdapterPolicy(
            "v1",
            {"groups": ("POST", "PATCH")},
            body_fields={"groups": ("name", "active", "roles")},
            required_permissions={"groups": ("admin.group",)},
        )
        self.plane = ControlPlane(
            self.ledger,
            self.policy,
            self.transport,
            resolver=lambda _: ["93.184.216.34"],
        )
        self.operation = Operation(
            "create-group",
            "POST",
            "groups",
            "managed-group",
            {"name": "Managed Group", "active": False},
            "low",
            "absent",
            "created-hash",
            rollback={"created": True, "postcondition": "inactive-hash"},
            required_permissions=("admin.group",),
        )

    def tearDown(self) -> None:
        self.plane.disconnect()
        self.ledger.close()
        self.directory.cleanup()

    def ready(self, operations: list[Operation] | None = None) -> None:
        self.plane.connect("https://tenant.example", "very-secret-token")
        preview = self.plane.make_preview(
            {"version": 1},
            {"graph": 1},
            operations or [self.operation],
            project_id="project-one",
        )
        self.plane.approve(preview.hash)

    def test_origin_identity_permission_and_credential_boundaries(self) -> None:
        for origin in (
            "http://tenant.example",
            "https://a..example",
            "https://bad-.example",
            "https://[:]/",
            "https://tenant.example:0",
            "https://tenant.example:65536",
        ):
            with self.subTest(origin=origin), self.assertRaises(ControlError):
                self.plane.connect(origin, "secret")
        for token in ("", "   ", "token with space"):
            with self.subTest(token_kind=len(token)), self.assertRaises(ControlError):
                self.plane.connect("https://tenant.example", token)

        normalized = self.plane.connect("HTTPS://Tenant.Example./", "secret")
        self.assertEqual(normalized.origin, "https://tenant.example")
        self.plane.disconnect()

        private = FakeTransport()
        private.identity["canonical_origin"] = "https://127.0.0.1"
        private.identity["resolved_addresses"] = ["127.0.0.1"]
        private_plane = ControlPlane(self.ledger, self.policy, private)
        with self.assertRaisesRegex(ControlError, "explicit on-prem policy"):
            private_plane.connect("https://127.0.0.1", "secret")
        self.assertEqual(private.calls, [])

        invalid = FakeTransport()
        invalid.identity["actor"] = ""
        invalid_plane = ControlPlane(
            self.ledger,
            self.policy,
            invalid,
            resolver=lambda _: ["93.184.216.34"],
        )
        with self.assertRaisesRegex(ControlError, "claims are incomplete"):
            invalid_plane.connect("https://tenant.example", "temporary-secret")
        failed_credential = invalid.calls[0][1]["credential"]
        self.assertTrue(failed_credential.closed)

        self.ready()
        self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        dump = "".join(map(str, self.ledger.db.iterdump()))
        self.assertNotIn("very-secret-token", dump)
        self.assertNotIn(
            "very-secret-token",
            "".join(repr(kwargs) for _, kwargs in self.transport.calls),
        )
        self.assertEqual(self.ledger.state("run-one"), "applied")

    def test_preview_is_deeply_immutable_one_time_and_policy_bound(self) -> None:
        nested = Operation(
            "nested",
            "POST",
            "groups",
            "nested-target",
            {"roles": [{"name": "reader"}]},
            "low",
            "absent",
            "nested-hash",
            rollback={"created": True},
            required_permissions=("admin.group",),
        )
        self.ready([nested])
        with self.assertRaises(TypeError):
            nested.body["roles"][0]["name"] = "administrator"  # type: ignore[index]
        self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        with self.assertRaisesRegex(ControlError, "approval"):
            self.plane.apply("run-two", {"version": 1}, {"graph": 1})

        second = ControlPlane(
            self.ledger,
            self.policy,
            FakeTransport(),
            resolver=lambda _: ["93.184.216.34"],
        )
        second.connect("https://tenant.example", "secret")
        preview = second.make_preview(
            {"version": 1}, {"graph": 1}, [self.operation], project_id="p2"
        )
        second.approve(preview.hash)
        second.policy = AdapterPolicy(
            "v2",
            {"groups": ("POST",)},
            body_fields={"groups": ("name", "active", "roles")},
            required_permissions={"groups": ("admin.group",)},
        )
        with self.assertRaisesRegex(ControlError, "approval"):
            second.apply("run-policy", {"version": 1}, {"graph": 1})
        second.disconnect()

    def test_dependencies_are_topological_and_cycles_fail(self) -> None:
        dependent = Operation(
            "second",
            "PATCH",
            "groups",
            "second-target",
            {},
            "low",
            "before-two",
            "after-two",
            depends_on=("create-group",),
            rollback={"preimage": {}, "postcondition": "before-two"},
            required_permissions=("admin.group",),
        )
        self.ready([dependent, self.operation])
        self.plane.apply("ordered-run", {"version": 1}, {"graph": 1})
        writes = [
            kwargs["operation"].id
            for kind, kwargs in self.transport.calls
            if kind == "write"
        ]
        self.assertEqual(writes, ["create-group", "second"])

        cyclic = Operation(
            "cycle",
            "POST",
            "groups",
            "cycle-target",
            {},
            "low",
            "before",
            "after",
            depends_on=("cycle",),
        )
        other = ControlPlane(
            self.ledger,
            self.policy,
            FakeTransport(),
            resolver=lambda _: ["93.184.216.34"],
        )
        other.connect("https://tenant.example", "secret")
        with self.assertRaisesRegex(ControlError, "self dependency"):
            other.make_preview({}, {}, [cyclic])
        other.disconnect()

    def test_ambiguous_write_reconciles_and_verify_is_separate(self) -> None:
        self.transport.ambiguous = True
        self.ready()
        self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        call_kinds = [kind for kind, _ in self.transport.calls]
        self.assertIn("reconcile", call_kinds)
        self.assertEqual(self.plane.session_state, "applied")
        self.plane.verify("run-one")
        self.assertEqual(self.plane.session_state, "verified")
        self.assertEqual(self.ledger.state("run-one"), "verified")

    def test_unresolved_intent_blocks_rollback_until_reconciled(self) -> None:
        self.transport.bad_readback = True
        self.ready()
        with self.assertRaisesRegex(ControlError, "readback"):
            self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.assertEqual(self.ledger.state("run-one"), "outcome_ambiguous")
        with self.assertRaisesRegex(ControlError, "reconciled"):
            self.plane.rollback("run-one")
        self.transport.bad_readback = False
        self.plane.reconcile("run-one")
        self.assertEqual(self.ledger.state("run-one"), "applied")
        self.plane.rollback("run-one")
        self.assertEqual(self.ledger.state("run-one"), "rolled_back")

    def test_durable_preview_resumes_after_a_new_control_plane(self) -> None:
        self.transport.bad_readback = True
        self.ready()
        with self.assertRaises(ControlError):
            self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.assertEqual(self.ledger.purge_evidence(float("inf")), 0)
        self.assertIsNotNone(self.ledger.load_preview(self.plane.preview.hash))
        self.plane.disconnect()

        resumed_transport = FakeTransport()
        resumed = ControlPlane(
            self.ledger,
            self.policy,
            resumed_transport,
            resolver=lambda _: ["93.184.216.34"],
        )
        resumed.connect("https://tenant.example", "replacement-token")
        self.assertEqual(resumed.recoverable_runs()[0]["run_id"], "run-one")
        resumed.resume_run("run-one")
        resumed.reconcile("run-one")
        self.assertEqual(self.ledger.state("run-one"), "applied")
        resumed.rollback("run-one")
        resumed.disconnect()

    def test_authorization_failure_after_begin_has_a_recovery_state(self) -> None:
        second = Operation(
            "second",
            "PATCH",
            "groups",
            "second-target",
            {},
            "low",
            "before-two",
            "after-two",
            depends_on=("create-group",),
            rollback={"preimage": {"active": False}, "postcondition": "before-two"},
            required_permissions=("admin.group",),
        )
        self.ready([self.operation, second])
        self.transport.authorization_changes_after_writes = True
        with self.assertRaisesRegex(ControlError, "binding changed"):
            self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.assertEqual(self.ledger.state("run-one"), "partially_applied")
        self.transport.authorization_changes_after_writes = False
        self.plane.rollback("run-one")
        self.assertEqual(self.ledger.state("run-one"), "rolled_back")

    def test_ambiguous_write_can_be_proven_not_applied(self) -> None:
        self.transport.write_raises_before_mutation = True
        self.ready()
        with self.assertRaisesRegex(ControlError, "reconciliation is required"):
            self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.transport.reconcile_not_applied = True
        self.plane.reconcile("run-one")
        self.assertEqual(self.ledger.state("run-one"), "partially_applied")
        self.assertEqual(self.ledger.unresolved_intents("run-one"), set())
        self.plane.rollback("run-one")
        self.assertEqual(self.ledger.state("run-one"), "rolled_back")

    def test_fence_change_during_readback_prevents_durable_success(self) -> None:
        self.ready()
        transport = self.transport

        def replace_fence(kind: str, **kwargs: object) -> dict[str, object]:
            response = transport(kind, **kwargs)
            if kind == "readback":
                self.ledger.db.execute(
                    "UPDATE locks SET fence='replacement-fence' WHERE project='project-one'"
                )
            return response

        self.plane.transport = replace_fence
        with self.assertRaisesRegex(ControlError, "fencing token changed"):
            self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.assertEqual(self.ledger.state("run-one"), "outcome_ambiguous")
        self.assertEqual(self.ledger.outcomes("run-one"), {})
        self.plane.transport = transport
        self.plane.reconcile("run-one")
        self.plane.rollback("run-one")

    def test_incomplete_run_blocks_a_different_run_after_lease_expiry(self) -> None:
        self.transport.bad_readback = True
        self.ready()
        with self.assertRaises(ControlError):
            self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.ledger.db.execute("UPDATE locks SET expires=0")

        second_transport = FakeTransport()
        second = ControlPlane(
            self.ledger,
            self.policy,
            second_transport,
            resolver=lambda _: ["93.184.216.34"],
        )
        second.connect("https://tenant.example", "replacement-token")
        preview = second.make_preview(
            {"version": 1},
            {"graph": 1},
            [self.operation],
            project_id="project-one",
        )
        second.approve(preview.hash)
        with self.assertRaisesRegex(ControlError, "incomplete run"):
            second.apply("run-two", {"version": 1}, {"graph": 1})
        self.assertEqual(self.ledger.state("run-one"), "outcome_ambiguous")
        self.assertNotIn("write", [kind for kind, _ in second_transport.calls])
        second.disconnect()

        self.transport.bad_readback = False
        self.plane.reconcile("run-one")
        self.plane.rollback("run-one")

    def test_expired_lease_is_safely_reacquired_for_verification(self) -> None:
        self.ready()
        self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.ledger.db.execute("UPDATE locks SET expires=0")
        self.plane.verify("run-one")
        self.assertEqual(self.ledger.state("run-one"), "verified")

    def test_rollback_reconciles_response_loss_after_remote_inverse(self) -> None:
        self.ready()
        self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.transport.rollback_applied_then_raises = True
        with self.assertRaisesRegex(ControlError, "ambiguous"):
            self.plane.rollback("run-one")
        self.assertEqual(self.ledger.state("run-one"), "manual_recovery")
        self.plane.rollback("run-one")
        self.assertEqual(self.ledger.state("run-one"), "rolled_back")

    def test_rollback_uses_only_durable_applied_operations_in_reverse(self) -> None:
        second = Operation(
            "second",
            "PATCH",
            "groups",
            "second-target",
            {},
            "low",
            "before-two",
            "after-two",
            depends_on=("create-group",),
            rollback={"preimage": {"active": False}, "postcondition": "before-two"},
            required_permissions=("admin.group",),
        )
        self.ready([second, self.operation])
        with self.assertRaisesRegex(ControlError, "run"):
            self.plane.rollback("never-applied")
        self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.plane.rollback("run-one")
        rollbacks = [
            kwargs["operation"].id
            for kind, kwargs in self.transport.calls
            if kind == "rollback"
        ]
        self.assertEqual(rollbacks, ["second", "create-group"])
        self.assertEqual(self.ledger.state("run-one"), "rolled_back")

    def test_operational_row_tampering_never_authorizes_rollback(self) -> None:
        corruptions = [
            ("UPDATE runs SET state='verified' WHERE run_id='run-one'", ()),
            ("DELETE FROM intents WHERE run_id='run-one'", ()),
            (
                (
                    "UPDATE outcomes SET postimage_hash='forged-current' "
                    "WHERE run_id='run-one'"
                ),
                (),
            ),
            (
                (
                    "INSERT INTO intent_resolutions VALUES "
                    "('run-one','create-group','not_applied','absent',1.0)"
                ),
                (),
            ),
            (
                (
                    "INSERT INTO rollback_intents VALUES "
                    "('run-one','create-group','inactive-hash',1.0)"
                ),
                (),
            ),
        ]
        for statement, parameters in corruptions:
            with self.subTest(statement=statement), tempfile.TemporaryDirectory() as directory:
                ledger = Ledger(
                        os.path.join(directory, "tamper.sqlite3"),
                        InMemoryKeyProvider(b"t" * 32),
                    )
                transport = FakeTransport()
                plane = ControlPlane(
                        ledger,
                        self.policy,
                        transport,
                        resolver=lambda _: ["93.184.216.34"],
                )
                plane.connect("https://tenant.example", "temporary-token")
                preview = plane.make_preview(
                        {"version": 1},
                        {"graph": 1},
                        [self.operation],
                        project_id="project-one",
                )
                plane.approve(preview.hash)
                plane.apply("run-one", {"version": 1}, {"graph": 1})
                ledger.db.execute(statement, parameters)

                with self.assertRaisesRegex(ControlError, "authenticated audit"):
                    plane.rollback("run-one")
                self.assertNotIn("rollback", [kind for kind, _ in transport.calls])
                plane.disconnect()
                ledger.close()

    def test_deleting_authenticated_recovery_rows_fails_closed(self) -> None:
        self.transport.write_raises_before_mutation = True
        self.ready()
        with self.assertRaises(ControlError):
            self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.transport.reconcile_not_applied = True
        self.plane.reconcile("run-one")
        self.ledger.db.execute(
            "DELETE FROM intent_resolutions WHERE run_id='run-one'"
        )
        with self.assertRaisesRegex(ControlError, "authenticated audit"):
            self.plane.rollback("run-one")

    def test_deleting_authenticated_rollback_intent_fails_closed(self) -> None:
        self.ready()
        self.plane.apply("run-one", {"version": 1}, {"graph": 1})
        self.ledger.rollback_intent(
            "run-one", self.operation.id, "inactive-hash"
        )
        self.ledger.db.execute(
            "DELETE FROM rollback_intents WHERE run_id='run-one'"
        )
        with self.assertRaisesRegex(ControlError, "authenticated audit"):
            self.plane.rollback("run-one")

    def test_authenticated_rows_must_still_match_the_protected_preview(self) -> None:
        self.ready()
        preview = self.plane.preview
        assert preview is not None
        self.ledger.acquire_lock(
            preview.project_id, "run-one", preview.hash, self.policy.lease_seconds
        )
        self.ledger.begin_run(
            "run-one",
            preview.hash,
            preview.tenant_fingerprint,
            preview.project_id,
        )
        forged = Operation(
            self.operation.id,
            self.operation.method,
            self.operation.path_class,
            self.operation.target,
            self.operation.body,
            self.operation.risk,
            self.operation.precondition,
            "forged-postimage",
            rollback=self.operation.rollback,
            required_permissions=self.operation.required_permissions,
        )
        self.ledger.intent("run-one", forged)
        self.ledger.outcome("run-one", forged.id, forged.postcondition)
        self.ledger.set_state("run-one", "applied")

        with self.assertRaisesRegex(ControlError, "protected preview"):
            self.plane.rollback("run-one")
        self.assertNotIn("rollback", [kind for kind, _ in self.transport.calls])

    def test_pagination_encryption_audit_permissions_and_lock(self) -> None:
        self.assertFalse(
            CapabilityDiscovery.pages(
                lambda _: (200, [{"id": 1}] * 100), max_pages=3
            ).complete
        )
        self.assertFalse(CapabilityDiscovery.pages(lambda _: (403, [])).complete)
        self.assertTrue(CapabilityDiscovery.pages(lambda _: (200, [])).complete)

        self.ledger.put_blob("evidence", b"plaintext evidence")
        raw = self.ledger.db.execute("SELECT ciphertext FROM blobs").fetchone()[0]
        self.assertNotIn(b"plaintext evidence", raw)
        self.assertEqual(self.ledger.get_blob("evidence"), b"plaintext evidence")
        self.assertEqual(self.ledger.purge_evidence(float("inf")), 1)
        self.assertTrue(self.ledger.verify_audit_chain())
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

        denied_transport = FakeTransport()
        denied_transport.identity["permissions"] = []
        denied = ControlPlane(
            self.ledger,
            self.policy,
            denied_transport,
            resolver=lambda _: ["93.184.216.34"],
        )
        denied.connect("https://tenant.example", "secret")
        undeclared = Operation(
            "undeclared",
            "POST",
            "groups",
            "undeclared-target",
            {},
            "low",
            "absent",
            "after",
        )
        with self.assertRaisesRegex(ControlError, "missing required permission"):
            denied.make_preview({}, {}, [undeclared])
        denied.disconnect()

        last_sequence = self.ledger.db.execute(
            "SELECT MAX(sequence) FROM audit"
        ).fetchone()[0]
        self.ledger.db.execute("DELETE FROM audit WHERE sequence=?", (last_sequence,))
        self.assertFalse(self.ledger.verify_audit_chain())

    def test_ledger_rejects_world_writable_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, stat.S_IRWXU | stat.S_IWOTH)
            with self.assertRaisesRegex(ControlError, "owner-controlled"):
                Ledger(
                    os.path.join(directory, "unsafe.sqlite3"),
                    InMemoryKeyProvider(b"z" * 32),
                )

    def test_committed_audit_extension_recovers_after_anchor_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "recoverable.sqlite3")
            provider = FlakyAnchorProvider(b"a" * 32)
            ledger = Ledger(path, provider)
            provider.fail_updates = 1
            with self.assertRaisesRegex(ControlError, "anchor could not be advanced"):
                ledger.audit("run", "event", {"safe": True})
            self.assertEqual(
                ledger.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 1
            )
            ledger.close()

            reopened = Ledger(path, provider)
            self.assertTrue(reopened.verify_audit_chain())
            reopened.close()
if __name__ == "__main__":
    unittest.main()
