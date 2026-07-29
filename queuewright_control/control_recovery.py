"""Verification, reconciliation, rollback, and transport mixin."""

from __future__ import annotations

from typing import Any, Mapping, NoReturn

from .models import Connection, ControlError, EphemeralCredential, Operation, Preview, _hash

class ControlRecoveryMixin:
    def verify(self, run_id: str) -> None:
        preview = self._run_preview(run_id, {"applied"})
        connection, credential = self._require_connection()
        fence = self.ledger.ensure_lock(
            preview.project_id,
            run_id,
            preview.hash,
            self.policy.lease_seconds,
        )
        outcomes = self.ledger.outcomes(run_id)
        if set(outcomes) != {operation.id for operation in preview.operations}:
            self.ledger.set_state(run_id, "manual_recovery")
            self.session_state = "manual_recovery"
            raise ControlError(
                "verification_incomplete",
                "/verify",
                "durable applied-operation evidence is incomplete",
                run_id,
            )
        for operation in preview.operations:
            self._reauthorize(operation, fence)
            self._assert_run_fence(preview, run_id, fence)
            evidence = self._transport(
                "verify",
                connection,
                credential,
                operation=operation,
                fencing_token=fence,
            )
            self._assert_run_fence(preview, run_id, fence)
            if not isinstance(evidence, Mapping) or evidence.get("hash") != outcomes[operation.id]:
                self.ledger.set_state(run_id, "drift_detected")
                self.session_state = "drift_detected"
                raise ControlError(
                    "verification_failed",
                    "/verify",
                    "fresh verification found drift or incomplete evidence",
                    run_id,
                )
        self._assert_run_fence(preview, run_id, fence)
        self.ledger.set_state(run_id, "verified")
        self.session_state = "verified"
        self.ledger.release_lock(preview.project_id, run_id, preview.hash)

    def reconcile(self, run_id: str) -> None:
        """Resolve every durable intent whose write outcome is still unknown."""
        preview = self._run_preview(run_id, {"outcome_ambiguous"})
        connection, credential = self._require_connection()
        fence = self.ledger.ensure_lock(
            preview.project_id,
            run_id,
            preview.hash,
            self.policy.lease_seconds,
        )
        by_id = {operation.id: operation for operation in preview.operations}
        for operation_id in sorted(self.ledger.unresolved_intents(run_id)):
            self._reconcile_operation(
                run_id, preview, connection, credential, fence, by_id, operation_id
            )
        self._finish_reconciliation(run_id, preview, fence)

    def _reconcile_operation(
        self, run_id: str, preview: Preview, connection: Connection,
        credential: EphemeralCredential, fence: str,
        by_id: Mapping[str, Operation], operation_id: str,
    ) -> None:
        operation = by_id.get(operation_id)
        if operation is None:
            self._manual_recovery(run_id, "/reconcile", "durable intent is absent from the protected preview")
        self._reauthorize(operation, fence)
        self._assert_run_fence(preview, run_id, fence)
        reconciled = self._transport("reconcile", connection, credential, operation=operation, fencing_token=fence)
        self._assert_run_fence(preview, run_id, fence)
        if not isinstance(reconciled, Mapping):
            self._manual_recovery(run_id, "/reconcile", "ambiguous write could not be proven")
        if reconciled.get("matched") is False and reconciled.get("hash") == operation.precondition:
            self.ledger.resolve_not_applied(run_id, operation.id, operation.precondition)
            return
        if not (reconciled.get("matched") is True and reconciled.get("hash") == operation.postcondition):
            self._manual_recovery(run_id, "/reconcile", "ambiguous write matched neither approved preimage nor postimage")
        self._record_reconciled_outcome(run_id, preview, connection, credential, fence, operation)

    def _record_reconciled_outcome(
        self, run_id: str, preview: Preview, connection: Connection,
        credential: EphemeralCredential, fence: str, operation: Operation,
    ) -> None:
        readback = self._transport("readback", connection, credential, operation=operation, fencing_token=fence)
        self._assert_run_fence(preview, run_id, fence)
        if not isinstance(readback, Mapping) or readback.get("hash") != operation.postcondition:
            self._manual_recovery(run_id, "/reconcile", "reconciled write failed authoritative readback")
        self.ledger.outcome(run_id, operation.id, operation.postcondition)

    def _finish_reconciliation(self, run_id: str, preview: Preview, fence: str) -> None:
        self._assert_run_fence(preview, run_id, fence)
        state = "applied" if set(self.ledger.outcomes(run_id)) == {operation.id for operation in preview.operations} else "partially_applied"
        self.ledger.set_state(run_id, state)
        self.session_state = state

    def _manual_recovery(self, run_id: str, path: str, message: str) -> NoReturn:
        self.ledger.set_state(run_id, "manual_recovery")
        self.session_state = "manual_recovery"
        raise ControlError("manual_recovery", path, message, run_id)

    def detect_drift(self, run_id: str, current_baseline: Any) -> bool:
        preview = self.preview
        if not preview or _hash(current_baseline) == preview.baseline_hash:
            return False
        if self.ledger.run(run_id):
            self.ledger.set_state(run_id, "drift_detected")
        self.session_state = "drift_detected"
        return True

    def rollback(self, run_id: str) -> None:
        preview = self._run_preview(
            run_id,
            {
                "applied",
                "verified",
                "drift_detected",
                "outcome_ambiguous",
                "partially_applied",
                "rolling_back",
                "manual_recovery",
            },
        )
        connection, credential = self._require_connection()
        fence = self.ledger.ensure_lock(
            preview.project_id,
            run_id,
            preview.hash,
            self.policy.lease_seconds,
        )
        outcomes = self.ledger.outcomes(run_id)
        if self.ledger.unresolved_intents(run_id):
            raise ControlError(
                "outcome_ambiguous",
                "/rollback",
                "ambiguous writes must be reconciled before rollback",
                run_id,
            )
        if not outcomes:
            self._assert_run_fence(preview, run_id, fence)
            self.ledger.set_state(run_id, "rolled_back")
            self.session_state = "rolled_back"
            self.ledger.release_lock(preview.project_id, run_id, preview.hash)
            return
        self._set_rollback_state(run_id, "rolling_back")
        rollback_intents = self.ledger.rollback_intents(run_id)
        for operation in reversed(preview.operations):
            if operation.id not in outcomes:
                continue
            fence = self._rollback_operation(run_id, preview, fence, operation, outcomes, rollback_intents)
        self._assert_run_fence(preview, run_id, fence)
        self._set_rollback_state(run_id, "rolled_back")
        self.ledger.release_lock(preview.project_id, run_id, preview.hash)

    def _set_rollback_state(self, run_id: str, state: str) -> None:
        self.ledger.set_state(run_id, state)
        self.session_state = state

    def _rollback_operation(
        self, run_id: str, preview: Preview, fence: str, operation: Operation,
        outcomes: Mapping[str, str], rollback_intents: Mapping[str, str],
    ) -> str:
        connection, credential = self._require_connection()
        fence = self.ledger.ensure_lock(preview.project_id, run_id, preview.hash, self.policy.lease_seconds)
        self._reauthorize(operation, fence)
        current = self._current_hash(preview, run_id, connection, credential, fence, operation)
        expected = operation.rollback.get("postcondition", operation.precondition)
        if isinstance(current, Mapping) and current.get("hash") == expected and rollback_intents.get(operation.id) == expected:
            self.ledger.mark_rolled_back(run_id, operation.id)
            return fence
        if not isinstance(current, Mapping) or current.get("hash") != outcomes[operation.id]:
            self._manual_recovery(run_id, "/rollback", "resource changed after apply; automatic rollback stopped")
        self._write_rollback(run_id, preview, connection, credential, fence, operation, expected)
        return fence

    def _current_hash(
        self, preview: Preview, run_id: str, connection: Connection,
        credential: EphemeralCredential, fence: str, operation: Operation,
    ) -> Any:
        self._assert_run_fence(preview, run_id, fence)
        result = self._transport("current_hash", connection, credential, operation=operation, fencing_token=fence)
        self._assert_run_fence(preview, run_id, fence)
        return result

    def _write_rollback(
        self, run_id: str, preview: Preview, connection: Connection,
        credential: EphemeralCredential, fence: str, operation: Operation, expected: Any,
    ) -> None:
        action = self._rollback_action(run_id, operation)
        self.ledger.rollback_intent(run_id, operation.id, str(expected))
        try:
            result = self._transport("rollback", connection, credential, operation=operation, action=action, fencing_token=fence)
        except Exception:
            self._manual_recovery(run_id, "/rollback", "rollback outcome is ambiguous and must be reconciled")
        readback = self._current_hash(preview, run_id, connection, credential, fence, operation)
        if not isinstance(result, Mapping) or result.get("hash") != expected or not isinstance(readback, Mapping) or readback.get("hash") != expected:
            self._manual_recovery(run_id, "/rollback", "rollback readback failed")
        self.ledger.mark_rolled_back(run_id, operation.id)

    def _rollback_action(self, run_id: str, operation: Operation) -> str:
        if operation.rollback.get("created") is True:
            return "deactivate"
        if operation.rollback.get("preimage") is None:
            self._manual_recovery(run_id, "/rollback", "operation has no approved inverse")
        return "restore"
