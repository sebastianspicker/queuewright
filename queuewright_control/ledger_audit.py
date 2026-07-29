"""Authenticated audit-chain and recovery mixin for Ledger."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from typing import Any, Mapping

from .models import (
    ControlError, OperationalFacts, RESERVED_AUDIT_KINDS,
    _canonical_bytes, _strict_json,
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
        last = self.db.execute(
            "SELECT sequence, entry_mac FROM audit ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = (last[0] + 1) if last else 1
        previous = last[1] if last else "0" * 64
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
            "INSERT INTO audit VALUES (?, ?, ?, ?, ?, ?, ?)",
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
        previous = "0" * 64
        expected_sequence = 1
        entries: dict[int, str] = {}
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
            previous = entry
            expected_sequence += 1
        if not entries:
            return None, entries
        head_sequence = expected_sequence - 1
        return (head_sequence, entries[head_sequence]), entries

    def verify_audit_chain(self) -> bool:
        try:
            head, _ = self._audit_chain()
        except (ControlError, json.JSONDecodeError, TypeError, ValueError):
            return False
        anchor = self._key_provider.get_audit_anchor()
        return anchor == head

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
        if not self.verify_audit_chain():
            raise ControlError(
                "ledger_integrity",
                "/ledger/audit",
                "audit chain or protected head is invalid",
            )
        try:
            expected = self._expected_operational_rows()
            actual = self._actual_operational_rows()
        except (json.JSONDecodeError, TypeError, ValueError, sqlite3.DatabaseError) as error:
            raise ControlError("ledger_integrity", "/ledger", "operational ledger evidence is malformed") from error
        if actual != expected:
            raise ControlError("ledger_integrity", "/ledger", "operational rows do not match the authenticated audit record")

    def _expected_operational_rows(self) -> tuple[Any, ...]:
        expected_runs: dict[str, tuple[str, str, str, str]] = {}
        expected_intents: dict[tuple[str, str], str] = {}
        expected_outcomes: dict[tuple[str, str], tuple[str, str]] = {}
        expected_resolutions: dict[tuple[str, str], tuple[str, str]] = {}
        expected_rollbacks: dict[tuple[str, str], str] = {}
        try:
            audit_rows = self.db.execute(
                "SELECT run_id,kind,metadata FROM audit ORDER BY sequence"
            )
            for run_id, kind, encoded in audit_rows:
                facts = OperationalFacts(expected_runs, expected_intents, expected_outcomes, expected_resolutions, expected_rollbacks)
                self._apply_audit_fact(str(run_id), str(kind), json.loads(encoded), facts)

            return (expected_runs, expected_intents, expected_outcomes, expected_resolutions, expected_rollbacks)
        except (json.JSONDecodeError, TypeError, ValueError, sqlite3.DatabaseError):
            raise

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
