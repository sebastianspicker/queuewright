"""Authenticated-ledger cache, tamper, and concurrency contracts."""

from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path

from control_test_support import FlakyAnchorProvider
from queuewright_control import ControlError, InMemoryKeyProvider, Ledger, Operation
from queuewright_control.models import LEDGER_SCHEMA


def _operation(identifier: str) -> Operation:
    return Operation(
        identifier,
        "POST",
        "groups",
        identifier,
        {"name": identifier},
        "low",
        "absent",
        f"{identifier}-created",
        rollback={"created": True, "postcondition": f"{identifier}-inactive"},
        required_permissions=("admin.group",),
    )


class LedgerIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "ledger.sqlite3")
        self.provider = InMemoryKeyProvider(b"l" * 32)
        self.ledger = Ledger(self.path, self.provider)

    def tearDown(self) -> None:
        self.ledger.close()
        self.directory.cleanup()

    def _seed_run(self, run_id: str = "run") -> None:
        self.ledger.begin_run(run_id, "preview", "tenant", "project")

    def _second_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def test_reserved_fact_transitions_remain_replayable(self) -> None:
        self._seed_run()
        applied = _operation("applied")
        absent = _operation("absent")
        self.ledger.intent("run", applied)
        self.ledger.outcome("run", applied.id, applied.postcondition)
        self.ledger.mark_rolled_back("run", applied.id)
        self.ledger.intent("run", absent)
        self.ledger.resolve_not_applied("run", absent.id, absent.precondition)
        self.ledger.rollback_intent("run", applied.id, "applied-inactive")
        self.ledger.set_state("run", "rolled_back")

        self.assertTrue(self.ledger.verify_audit_chain())
        reopened = Ledger(self.path, self.provider)
        try:
            self.assertEqual(reopened.state("run"), "rolled_back")
            self.assertEqual(reopened.not_applied_hashes("run"), {"absent": "absent"})
            self.assertEqual(
                reopened.rollback_intents("run"), {"applied": "applied-inactive"}
            )
        finally:
            reopened.close()

    def test_same_connection_operational_tamper_forces_full_replay(self) -> None:
        self._seed_run()
        self.ledger.db.execute("UPDATE runs SET state='verified' WHERE run_id='run'")
        with self.assertRaisesRegex(ControlError, "operational rows"):
            self.ledger.state("run")

    def test_second_connection_operational_tamper_forces_full_replay(self) -> None:
        self._seed_run()
        connection = self._second_connection()
        try:
            connection.execute("UPDATE runs SET state='verified' WHERE run_id='run'")
        finally:
            connection.close()
        with self.assertRaisesRegex(ControlError, "operational rows"):
            self.ledger.state("run")

    def test_prefix_tamper_truncation_and_forgery_fail_closed(self) -> None:
        for kind in ("prefix", "truncation", "forgery"):
            with self.subTest(kind=kind):
                path = os.path.join(self.directory.name, f"{kind}.sqlite3")
                provider = InMemoryKeyProvider(b"p" * 32)
                ledger = Ledger(path, provider)
                ledger.audit("run", "one", {"value": 1})
                ledger.audit("run", "two", {"value": 2})
                connection = sqlite3.connect(path, isolation_level=None)
                try:
                    if kind == "prefix":
                        connection.execute(
                            "UPDATE audit SET metadata='{}' WHERE sequence=1"
                        )
                    elif kind == "truncation":
                        connection.execute("DELETE FROM audit WHERE sequence=2")
                    else:
                        connection.execute(
                            "INSERT INTO audit VALUES (3,'run','forged','{}',"
                            "(SELECT entry_mac FROM audit WHERE sequence=2),?,?)",
                            ("0" * 64, time.time()),
                        )
                finally:
                    connection.close()
                self.assertFalse(ledger.verify_audit_chain())
                with self.assertRaises(ControlError):
                    ledger.audit("run", "next", {"safe": True})
                ledger.close()

    def test_anchor_divergence_and_lag(self) -> None:
        self.ledger.audit("run", "one", {"value": 1})
        first = self.provider.get_audit_anchor()
        self.ledger.audit("run", "two", {"value": 2})
        self.provider._audit_anchor = first
        reopened = Ledger(self.path, self.provider)
        try:
            self.assertTrue(reopened.verify_audit_chain())
        finally:
            reopened.close()

        self.provider._audit_anchor = (1, "f" * 64)
        with self.assertRaisesRegex(ControlError, "authenticated extension"):
            Ledger(self.path, self.provider)

    def test_anchor_cas_failure_invalidates_then_reopens(self) -> None:
        self.ledger.close()
        provider = FlakyAnchorProvider(b"c" * 32)
        self.ledger = Ledger(self.path, provider)
        provider.fail_updates = 1
        with self.assertRaisesRegex(ControlError, "anchor could not be advanced"):
            self.ledger.audit("run", "event", {"safe": True})
        self.assertIsNone(self.ledger._cache)
        self.ledger.close()
        self.ledger = Ledger(self.path, provider)
        self.assertTrue(self.ledger.verify_audit_chain())

    def test_failed_transaction_rolls_back_and_invalidates(self) -> None:
        self._seed_run()
        with self.assertRaisesRegex(ControlError, "already been used"):
            self._seed_run()
        self.assertFalse(self.ledger.db.in_transaction)
        self.assertIsNone(self.ledger._cache)
        self.ledger.audit("system", "after_rollback", {"safe": True})
        self.assertTrue(self.ledger.verify_audit_chain())

    def test_two_ledgers_alternate_appends(self) -> None:
        other = Ledger(self.path, self.provider)
        try:
            for index in range(10):
                (self.ledger if index % 2 == 0 else other).audit(
                    "run", "alternating", {"index": index}
                )
            self.assertTrue(self.ledger.verify_audit_chain())
            self.assertTrue(other.verify_audit_chain())
        finally:
            other.close()

    def test_postcommit_writer_is_included_before_cache_promotion(self) -> None:
        other = Ledger(self.path, self.provider)
        original = self.ledger._reconcile_committed_transaction
        raced = False

        def reconcile(transaction: object) -> None:
            nonlocal raced
            if not raced:
                raced = True
                other.audit("other", "raced", {"safe": True})
            original(transaction)

        self.ledger._reconcile_committed_transaction = reconcile
        try:
            self.ledger.audit("run", "event", {"safe": True})
            self.assertEqual(self.ledger._cache.head[0], 2)
            self.assertTrue(self.ledger.verify_audit_chain())
        finally:
            other.close()

    def test_promoted_stamps_are_captured_while_transaction_is_locked(self) -> None:
        original = self.ledger._database_stamp
        outside_calls: list[bool] = []

        def stamped():
            outside_calls.append(self.ledger.db.in_transaction)
            return original()

        self.ledger._database_stamp = stamped
        self.ledger.audit("run", "event", {"safe": True})
        self.assertTrue(all(outside_calls))

    def test_custom_trigger_disables_delta_fast_path(self) -> None:
        self._seed_run("first")
        self._seed_run("untouched")
        self.ledger.db.execute(
            "CREATE TRIGGER corrupt_untouched AFTER INSERT ON audit "
            "WHEN NEW.run_id='first' BEGIN "
            "UPDATE runs SET state='verified' WHERE run_id='untouched'; END"
        )
        with self.assertRaisesRegex(ControlError, "operational rows"):
            self.ledger.set_state("first", "verified")
        self.assertFalse(self.ledger.db.in_transaction)

    def test_changed_same_named_schema_disables_delta_fast_path(self) -> None:
        path = os.path.join(self.directory.name, "custom-schema.sqlite3")
        custom_schema = LEDGER_SCHEMA.replace(
            "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, state TEXT NOT NULL,",
            "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, state TEXT NOT NULL UNIQUE,",
        ).replace(
            "PRIMARY KEY(run_id, operation_id), FOREIGN KEY(run_id) REFERENCES runs(run_id));\n"
            "CREATE TABLE IF NOT EXISTS audit",
            "PRIMARY KEY(run_id, operation_id), FOREIGN KEY(run_id) REFERENCES runs(run_id), "
            "FOREIGN KEY(state) REFERENCES runs(state) ON UPDATE CASCADE);\n"
            "CREATE TABLE IF NOT EXISTS audit",
            1,
        )
        connection = sqlite3.connect(path)
        connection.executescript(custom_schema)
        connection.close()
        os.chmod(path, 0o600)
        ledger = Ledger(path, InMemoryKeyProvider(b"s" * 32))
        try:
            self.assertFalse(ledger._cache.standard_schema)
            operation = _operation("cascade")
            ledger.begin_run("custom", "preview", "tenant", "project")
            ledger.intent("custom", operation)
            ledger.set_state("custom", "applied")
            ledger.outcome("custom", operation.id, operation.postcondition)
            with self.assertRaisesRegex(ControlError, "operational rows"):
                ledger.set_state("custom", "verified")
            self.assertEqual(ledger.state("custom"), "applied")
        finally:
            ledger.close()

    def test_temporary_trigger_invalidates_standard_schema_cache(self) -> None:
        self._seed_run("first")
        self._seed_run("untouched")
        self.ledger.db.execute(
            "CREATE TEMP TRIGGER corrupt_untouched AFTER INSERT ON main.audit "
            "WHEN NEW.run_id='first' BEGIN "
            "UPDATE runs SET state='verified' WHERE run_id='untouched'; END"
        )
        with self.assertRaisesRegex(ControlError, "operational rows"):
            self.ledger.set_state("first", "verified")
        self.assertFalse(self.ledger.db.in_transaction)

    def test_verified_read_holds_snapshot_through_result_query(self) -> None:
        self._seed_run()
        original = self.ledger._ensure_verified_state
        writer_result: list[str] = []

        def writer() -> None:
            connection = sqlite3.connect(self.path, isolation_level=None, timeout=0.05)
            try:
                connection.execute("UPDATE runs SET state='verified' WHERE run_id='run'")
                writer_result.append("committed")
            except sqlite3.OperationalError:
                writer_result.append("blocked")
            finally:
                connection.close()

        def verified():
            state = original()
            thread = threading.Thread(target=writer)
            thread.start()
            thread.join()
            return state

        self.ledger._ensure_verified_state = verified
        self.assertEqual(self.ledger.state("run"), "applying")
        self.assertEqual(writer_result, ["blocked"])

    def test_verify_audit_chain_cleans_up_provider_failure(self) -> None:
        self.ledger.audit("run", "event", {"safe": True})
        original = self.provider.get_audit_anchor

        def unavailable():
            raise RuntimeError("provider unavailable")

        self.provider.get_audit_anchor = unavailable
        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            self.ledger.verify_audit_chain()
        self.assertFalse(self.ledger.db.in_transaction)
        self.provider.get_audit_anchor = original
        self.ledger.audit("run", "recovered", {"safe": True})

    def test_connection_safety_pragma_changes_fail_closed(self) -> None:
        for pragma, value in (
            ("foreign_keys", "OFF"),
            ("synchronous", "OFF"),
            ("journal_mode", "WAL"),
        ):
            with self.subTest(pragma=pragma):
                path = os.path.join(self.directory.name, f"pragma-{pragma}.sqlite3")
                ledger = Ledger(path, InMemoryKeyProvider(b"j" * 32))
                ledger.db.execute(f"PRAGMA {pragma}={value}")
                with self.assertRaisesRegex(ControlError, "safety settings"):
                    ledger.audit("run", "event", {"safe": True})
                self.assertFalse(ledger.db.in_transaction)
                ledger.close()

    def test_live_path_mode_replacement_and_symlink_changes_fail_closed(self) -> None:
        for kind in ("mode", "replacement", "symlink"):
            with self.subTest(kind=kind):
                path = os.path.join(self.directory.name, f"path-{kind}.sqlite3")
                provider = InMemoryKeyProvider(b"f" * 32)
                ledger = Ledger(path, provider)
                if kind == "mode":
                    os.chmod(path, 0o640)
                elif kind == "replacement":
                    replacement = f"{path}.replacement"
                    Path(replacement).touch(mode=0o600)
                    os.replace(replacement, path)
                else:
                    target = f"{path}.target"
                    Path(target).touch(mode=0o600)
                    os.unlink(path)
                    os.symlink(target, path)
                with self.assertRaisesRegex(ControlError, "ledger path"):
                    ledger.audit("run", "event", {"safe": True})
                ledger.close()

    def test_chained_symlink_target_is_validated_before_victim_is_touched(self) -> None:
        unsafe = Path(self.directory.name, "shared")
        victim_directory = Path(self.directory.name, "victim")
        unsafe.mkdir()
        victim_directory.mkdir()
        os.chmod(unsafe, 0o777)
        victim = victim_directory / "victim.sqlite3"
        connection = sqlite3.connect(victim)
        connection.execute("CREATE TABLE important (value TEXT NOT NULL)")
        connection.execute("INSERT INTO important VALUES ('preserve')")
        connection.commit()
        connection.close()
        os.chmod(victim, 0o640)
        (unsafe / "redirect").symlink_to(victim_directory, target_is_directory=True)
        entry = Path(self.directory.name, "entry")
        entry.symlink_to(unsafe / "redirect", target_is_directory=True)

        with self.assertRaisesRegex(ControlError, "ancestor is not trusted"):
            Ledger(entry / victim.name, self.provider)

        self.assertEqual(stat.S_IMODE(victim.stat().st_mode), 0o640)
        connection = sqlite3.connect(victim)
        try:
            self.assertEqual(
                connection.execute("SELECT value FROM important").fetchone()[0],
                "preserve",
            )
            self.assertEqual(
                {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_schema WHERE type='table'"
                    )
                },
                {"important"},
            )
        finally:
            connection.close()

    def test_memory_database_and_legacy_schema(self) -> None:
        memory = Ledger(":memory:", InMemoryKeyProvider(b"m" * 32))
        try:
            memory.audit("run", "event", {"safe": True})
            self.assertTrue(memory.verify_audit_chain())
        finally:
            memory.close()

        legacy_path = os.path.join(self.directory.name, "legacy.sqlite3")
        connection = sqlite3.connect(legacy_path)
        connection.executescript(LEDGER_SCHEMA)
        connection.close()
        os.chmod(legacy_path, 0o600)
        legacy = Ledger(legacy_path, InMemoryKeyProvider(b"g" * 32))
        try:
            names = {
                row[0]
                for row in legacy.db.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                )
            }
            self.assertEqual(names, Ledger._STANDARD_TABLES)
            legacy.audit("run", "legacy", {"safe": True})
        finally:
            legacy.close()

    def test_append_scaling_has_no_historical_replays_after_init(self) -> None:
        for count in (50, 100, 200):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                ledger = Ledger(
                    os.path.join(directory, "benchmark.sqlite3"),
                    InMemoryKeyProvider(b"b" * 32),
                )
                visits = {"chains": 0, "facts": 0}
                original_history = ledger._authenticated_history
                original_actual = ledger._actual_operational_rows

                def counted_history(
                    *, derive_facts, current_visits=visits,
                    current_history=original_history,
                ):
                    current_visits["chains"] += 1
                    return current_history(derive_facts=derive_facts)

                def counted_actual(
                    current_visits=visits, current_actual=original_actual
                ):
                    current_visits["facts"] += 1
                    return current_actual()

                ledger._authenticated_history = counted_history
                ledger._actual_operational_rows = counted_actual
                for index in range(count):
                    ledger.audit("benchmark", "append", {"index": index})
                self.assertEqual(visits, {"chains": 0, "facts": 0})
                self.assertEqual(
                    ledger.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0],
                    count,
                )
                self.assertEqual(ledger._cache.head[0], count)
                ledger.close()

    def test_public_audit_verification_always_scans_current_history(self) -> None:
        self.ledger.audit("run", "event", {"safe": True})
        original = self.ledger._audit_chain
        calls = 0

        def counted_chain():
            nonlocal calls
            calls += 1
            return original()

        self.ledger._audit_chain = counted_chain
        self.assertTrue(self.ledger.verify_audit_chain())
        self.assertTrue(self.ledger.verify_audit_chain())
        self.assertEqual(calls, 2)


class LedgerLockTests(unittest.TestCase):
    def test_expiry_renewal_reacquisition_and_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(
                os.path.join(directory, "locks.sqlite3"),
                InMemoryKeyProvider(b"q" * 32),
            )
            try:
                first = ledger.acquire_lock("project", "owner", "preview", 60)
                self.assertEqual(
                    ledger.renew_lock("project", "owner", "preview", 120), first
                )
                with self.assertRaisesRegex(ControlError, "already locked"):
                    ledger.acquire_lock("project", "other", "other-preview", 60)
                ledger.db.execute(
                    "UPDATE locks SET expires=? WHERE project='project'", (time.time() - 1,)
                )
                second = ledger.ensure_lock("project", "owner", "preview", 60)
                self.assertNotEqual(second, first)
                with self.assertRaisesRegex(ControlError, "ownership"):
                    ledger.release_lock("project", "other", "preview")
                ledger.release_lock("project", "owner", "preview")
                with self.assertRaises(ControlError):
                    ledger.assert_lock("project", "owner", "preview")
            finally:
                ledger.close()
