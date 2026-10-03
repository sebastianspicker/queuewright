"""Authenticated audit-chain and recovery mixin for Ledger."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from collections.abc import Mapping
from typing import Any

from .models import (
    RESERVED_AUDIT_KINDS,
    ControlError,
    OperationalFacts,
    _canonical_bytes,
    _strict_json,
)


class LedgerAuditMixin:
    def _audit_locked(
        self,
        run_id: str,
        kind: str,
        metadata: Mapping[str, Any],
        created: float | None = None,
    ) -> None:
        safe = _strict_json(metadata, "audit.metadata")
        transaction = self._transaction
        if transaction is None or not self.db.in_transaction:
            self._invalidate_cache()
            raise ControlError(
                "ledger_integrity", "/ledger/audit", "audit append requires a trusted transaction"
            )
        sequence = transaction.head[0] + 1 if transaction.head else 1
        previous = transaction.head[1] if transaction.head else "0" * 64
        timestamp = created if created is not None else time.time()
        material = {
            "sequence": sequence,
            "run_id": run_id,
            "kind": kind,
            "metadata": safe,
            "previous_mac": previous,
            "created": timestamp,
        }
        entry = hmac.new(
            self._audit_key, _canonical_bytes(material), hashlib.sha256
        ).hexdigest()
        self.db.execute(
            "INSERT INTO audit "
            "(sequence,run_id,kind,metadata,previous_mac,entry_mac,created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sequence,
                run_id,
                kind,
                json.dumps(safe, sort_keys=True, separators=(",", ":")),
                previous,
                entry,
                timestamp,
            ),
        )
        transaction.head = (sequence, entry)
        transaction.audit_entries += 1
        self._stage_audit_fact(transaction, run_id, kind, safe)

    def audit(self, run_id: str, kind: str, metadata: Mapping[str, Any]) -> None:
        if kind in RESERVED_AUDIT_KINDS:
            raise ControlError(
                "audit_invalid",
                "/ledger/audit",
                "reserved operational audit kinds are internal only",
            )
        self._begin()
        try:
            self._audit_locked(run_id, kind, metadata)
            self._commit()
        except Exception:
            self._rollback()
            raise

    def _audit_chain(self) -> tuple[tuple[int, str] | None, dict[int, str]]:
        head, entries, _ = self._authenticated_history(derive_facts=False)
        return head, entries

    def _authenticated_history(
        self, *, derive_facts: bool
    ) -> tuple[
        tuple[int, str] | None,
        dict[int, str],
        OperationalFacts | None,
    ]:
        previous = "0" * 64
        expected_sequence = 1
        entries: dict[int, str] = {}
        facts = OperationalFacts({}, {}, {}, {}, {}) if derive_facts else None
        for sequence, run_id, kind, metadata, prior, entry, created in self.db.execute(
            "SELECT sequence,run_id,kind,metadata,previous_mac,entry_mac,created "
            "FROM audit ORDER BY sequence"
        ):
            material = {
                "sequence": sequence,
                "run_id": run_id,
                "kind": kind,
                "metadata": json.loads(metadata),
                "previous_mac": prior,
                "created": created,
            }
            expected = hmac.new(
                self._audit_key, _canonical_bytes(material), hashlib.sha256
            ).hexdigest()
            if (
                sequence != expected_sequence
                or prior != previous
                or not hmac.compare_digest(entry, expected)
            ):
                raise ControlError(
                    "audit_invalid",
                    "/ledger/audit",
                    "audit chain authentication failed",
                )
            entries[int(sequence)] = str(entry)
            if facts is not None:
                self._apply_audit_fact(
                    str(run_id), str(kind), material["metadata"], facts
                )
            previous = entry
            expected_sequence += 1
        if not entries:
            return None, entries, facts
        head_sequence = expected_sequence - 1
        return (head_sequence, entries[head_sequence]), entries, facts

    def verify_audit_chain(self) -> bool:
        owns_transaction = not self.db.in_transaction
        try:
            self._database_stamp()
            if owns_transaction:
                self.db.execute("BEGIN")
            if owns_transaction:
                self.db.execute("SELECT 1 FROM main.sqlite_schema LIMIT 1").fetchone()
            head, _ = self._audit_chain()
            anchor = self._key_provider.get_audit_anchor()
            result = anchor == head
        except (
            ControlError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            sqlite3.DatabaseError,
        ):
            if owns_transaction and self.db.in_transaction:
                self.db.execute("ROLLBACK")
            return False
        except Exception:
            if owns_transaction and self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        try:
            if owns_transaction:
                self.db.execute("COMMIT")
            return result
        except sqlite3.DatabaseError:
            if owns_transaction and self.db.in_transaction:
                self.db.execute("ROLLBACK")
            return False

    def _synchronize_anchor(self) -> None:
        """Authenticate the chain and recover a committed extension via CAS."""
        head, entries = self._audit_chain()
        anchor = self._key_provider.get_audit_anchor()
        self._require_matching_anchor(head, anchor, entries)
        if head is None or anchor == head:
            return
        self._advance_anchor(anchor, head)

    @staticmethod
    def _require_matching_anchor(
        head: tuple[int, str] | None,
        anchor: tuple[int, str] | None,
        entries: Mapping[int, str],
    ) -> None:
        if head is None and anchor is not None:
            raise ControlError(
                "audit_anchor_mismatch", "/ledger/audit", "protected audit anchor has no matching ledger chain"
            )
        if head is not None and anchor is not None:
            sequence, entry_mac = anchor
            if sequence not in entries or not hmac.compare_digest(entries[sequence], entry_mac):
                raise ControlError(
                    "audit_anchor_mismatch", "/ledger/audit", "ledger is not an authenticated extension of the protected anchor"
                )

    def _advance_anchor(
        self, anchor: tuple[int, str] | None, head: tuple[int, str]
    ) -> None:
        if not self._key_provider.compare_and_set_audit_anchor(anchor, head):
            if self._key_provider.get_audit_anchor() == head:
                return
            raise ControlError(
                "audit_anchor_update_failed",
                "/ledger/audit-anchor",
                "protected audit anchor could not be advanced",
            )

    def _verify_operational_integrity(self) -> None:
        """Cross-check every recovery-authorizing row against anchored audit facts."""
        if self._transaction is not None:
            self._verify_transaction(self._transaction)
            return
        if self.db.in_transaction:
            self._invalidate_cache()
            raise ControlError("ledger_integrity", "/ledger", "untrusted ledger transaction")
        self.db.execute("BEGIN")
        try:
            self._ensure_verified_state()
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            self._invalidate_cache()
            raise

    def _full_verified_state(self, *, advance_anchor: bool = True) -> Any:
        """Replay the complete authenticated history and all operational rows."""
        try:
            head, entries, expected = self._authenticated_history(derive_facts=True)
            assert expected is not None
            anchor = self._key_provider.get_audit_anchor()
            self._require_matching_anchor(head, anchor, entries)
            actual = self._actual_operational_rows()
        except ControlError:
            raise
        except (json.JSONDecodeError, TypeError, ValueError, sqlite3.DatabaseError) as error:
            raise ControlError(
                "ledger_integrity", "/ledger", "operational ledger evidence is malformed"
            ) from error
        if actual != self._facts_tuple(expected):
            raise ControlError(
                "ledger_integrity",
                "/ledger",
                "operational rows do not match the authenticated audit record",
            )
        if advance_anchor and head is not None and anchor != head:
            self._advance_anchor(anchor, head)
        return self._new_verified_state(
            head, expected, self._database_stamp(), self._has_standard_schema()
        )

    def _expected_operational_rows(self) -> OperationalFacts:
        expected_runs: dict[str, tuple[str, str, str, str]] = {}
        expected_intents: dict[tuple[str, str], str] = {}
        expected_outcomes: dict[tuple[str, str], tuple[str, str]] = {}
        expected_resolutions: dict[tuple[str, str], tuple[str, str]] = {}
        expected_rollbacks: dict[tuple[str, str], str] = {}
        audit_rows = self.db.execute(
            "SELECT run_id,kind,metadata FROM audit ORDER BY sequence"
        )
        for run_id, kind, encoded in audit_rows:
            facts = OperationalFacts(expected_runs, expected_intents, expected_outcomes, expected_resolutions, expected_rollbacks)
            self._apply_audit_fact(str(run_id), str(kind), json.loads(encoded), facts)

        return OperationalFacts(
            expected_runs,
            expected_intents,
            expected_outcomes,
            expected_resolutions,
            expected_rollbacks,
        )

    @staticmethod
    def _facts_tuple(facts: OperationalFacts) -> tuple[Any, ...]:
        return (
            facts.runs,
            facts.intents,
            facts.outcomes,
            facts.resolutions,
            facts.rollbacks,
        )

    def _stage_audit_fact(
        self, transaction: Any, run_id: str, kind: str, metadata: Any
    ) -> None:
        deltas = transaction.deltas
        if kind == "operation_rolled_back":
            fact = self._require_audit_shape(
                metadata, {"operation_id"}, "rolled-back audit shape"
            )
            key = (run_id, str(fact["operation_id"]))
            previous = deltas.outcomes.get(key, transaction.base.facts.outcomes.get(key))
            if previous is None:
                raise ValueError("rollback without applied outcome")
            deltas.outcomes[key] = (previous[0], "rolled_back")
            return
        self._apply_audit_fact(run_id, kind, metadata, deltas)

    def _verify_operational_deltas(self, transaction: Any) -> None:
        deltas = transaction.deltas
        checks = (
            (deltas.runs, self._actual_runs_for),
            (deltas.intents, self._actual_intents_for),
            (deltas.outcomes, self._actual_outcomes_for),
            (deltas.resolutions, self._actual_resolutions_for),
            (deltas.rollbacks, self._actual_rollbacks_for),
        )
        for expected, loader in checks:
            if expected and loader(set(expected)) != expected:
                raise ControlError(
                    "ledger_integrity",
                    "/ledger",
                    "operational rows changed outside their authenticated audit facts",
                )

    def _actual_runs_for(
        self, keys: set[str]
    ) -> dict[str, tuple[str, str, str, str]]:
        return {
            key: tuple(str(value) for value in row)
            for key in keys
            if (row := self.db.execute(
                "SELECT state,preview_hash,tenant_fingerprint,project_id FROM runs WHERE run_id=?",
                (key,),
            ).fetchone()) is not None
        }

    def _actual_intents_for(
        self, keys: set[tuple[str, str]]
    ) -> dict[tuple[str, str], str]:
        return {
            key: str(row[0])
            for key in keys
            if (row := self.db.execute(
                "SELECT operation_hash FROM intents WHERE run_id=? AND operation_id=?",
                key,
            ).fetchone()) is not None
        }

    def _actual_outcomes_for(
        self, keys: set[tuple[str, str]]
    ) -> dict[tuple[str, str], tuple[str, str]]:
        return {
            key: (str(row[0]), str(row[1]))
            for key in keys
            if (row := self.db.execute(
                "SELECT postimage_hash,state FROM outcomes WHERE run_id=? AND operation_id=?",
                key,
            ).fetchone()) is not None
        }

    def _actual_resolutions_for(
        self, keys: set[tuple[str, str]]
    ) -> dict[tuple[str, str], tuple[str, str]]:
        return {
            key: (str(row[0]), str(row[1]))
            for key in keys
            if (row := self.db.execute(
                "SELECT resolution,proven_hash FROM intent_resolutions WHERE run_id=? AND operation_id=?",
                key,
            ).fetchone()) is not None
        }

    def _actual_rollbacks_for(
        self, keys: set[tuple[str, str]]
    ) -> dict[tuple[str, str], str]:
        return {
            key: str(row[0])
            for key in keys
            if (row := self.db.execute(
                "SELECT expected_hash FROM rollback_intents WHERE run_id=? AND operation_id=?",
                key,
            ).fetchone()) is not None
        }

    @staticmethod
    def _require_audit_shape(metadata: Any, required: set[str], detail: str) -> dict[str, Any]:
        if not isinstance(metadata, dict) or set(metadata) != required:
            raise ValueError(detail)
        return metadata

    def _apply_audit_fact(
        self, run_id: str, kind: str, metadata: Any, facts: OperationalFacts,
    ) -> None:
        handlers = {
            "state": lambda: self._state_fact(run_id, metadata, facts.runs),
            "intent": lambda: self._intent_fact(run_id, metadata, facts.intents),
            "operation_applied": lambda: self._outcome_fact(run_id, metadata, facts.outcomes),
            "operation_rolled_back": lambda: self._rolled_back_fact(run_id, metadata, facts.outcomes),
            "operation_not_applied": lambda: self._resolution_fact(run_id, metadata, facts.resolutions),
            "rollback_intent": lambda: self._rollback_fact(run_id, metadata, facts.rollbacks),
        }
        handler = handlers.get(kind)
        if handler:
            handler()

    def _state_fact(self, run_id: str, metadata: Any, runs: dict[str, tuple[str, str, str, str]]) -> None:
        fact = self._require_audit_shape(metadata, {"state", "preview_hash", "tenant_fingerprint", "project_id"}, "state audit shape")
        runs[run_id] = tuple(str(fact[name]) for name in ("state", "preview_hash", "tenant_fingerprint", "project_id"))

    def _intent_fact(self, run_id: str, metadata: Any, intents: dict[tuple[str, str], str]) -> None:
        fact = self._require_audit_shape(metadata, {"operation_id", "operation_hash"}, "intent audit shape")
        intents[(run_id, str(fact["operation_id"]))] = str(fact["operation_hash"])

    def _outcome_fact(self, run_id: str, metadata: Any, outcomes: dict[tuple[str, str], tuple[str, str]]) -> None:
        fact = self._require_audit_shape(metadata, {"operation_id", "postimage_hash"}, "outcome audit shape")
        outcomes[(run_id, str(fact["operation_id"]))] = (str(fact["postimage_hash"]), "applied")

    def _rolled_back_fact(self, run_id: str, metadata: Any, outcomes: dict[tuple[str, str], tuple[str, str]]) -> None:
        fact = self._require_audit_shape(metadata, {"operation_id"}, "rolled-back audit shape")
        key = (run_id, str(fact["operation_id"]))
        previous = outcomes.get(key)
        if previous is None:
            raise ValueError("rollback without applied outcome")
        outcomes[key] = (previous[0], "rolled_back")

    def _resolution_fact(self, run_id: str, metadata: Any, resolutions: dict[tuple[str, str], tuple[str, str]]) -> None:
        fact = self._require_audit_shape(metadata, {"operation_id", "proven_hash"}, "resolution audit shape")
        resolutions[(run_id, str(fact["operation_id"]))] = ("not_applied", str(fact["proven_hash"]))

    def _rollback_fact(self, run_id: str, metadata: Any, rollbacks: dict[tuple[str, str], str]) -> None:
        fact = self._require_audit_shape(metadata, {"operation_id", "expected_hash"}, "rollback intent audit shape")
        rollbacks[(run_id, str(fact["operation_id"]))] = str(fact["expected_hash"])

    def _actual_operational_rows(self) -> tuple[Any, ...]:
        actual_runs = {
            str(run_id): (str(state), str(preview), str(tenant), str(project))
            for run_id, state, preview, tenant, project in self.db.execute(
                "SELECT run_id,state,preview_hash,tenant_fingerprint,project_id FROM runs"
            )
        }
        actual_intents = {
            (str(run_id), str(operation_id)): str(operation_hash)
            for run_id, operation_id, operation_hash in self.db.execute(
                "SELECT run_id,operation_id,operation_hash FROM intents"
            )
        }
        actual_outcomes = {
            (str(run_id), str(operation_id)): (str(postimage), str(state))
            for run_id, operation_id, postimage, state in self.db.execute(
                "SELECT run_id,operation_id,postimage_hash,state FROM outcomes"
            )
        }
        actual_resolutions = {
            (str(run_id), str(operation_id)): (str(resolution), str(proven_hash))
            for run_id, operation_id, resolution, proven_hash in self.db.execute(
                "SELECT run_id,operation_id,resolution,proven_hash FROM intent_resolutions"
            )
        }
        actual_rollbacks = {
            (str(run_id), str(operation_id)): str(expected_hash)
            for run_id, operation_id, expected_hash in self.db.execute(
                "SELECT run_id,operation_id,expected_hash FROM rollback_intents"
            )
        }
        return (actual_runs, actual_intents, actual_outcomes, actual_resolutions, actual_rollbacks)
