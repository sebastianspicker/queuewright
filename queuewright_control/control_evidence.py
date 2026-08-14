"""Control-plane state and durable-evidence validation mixin."""

from __future__ import annotations

import secrets
import time
from typing import Any, Mapping

from .models import Connection, ControlError, EphemeralCredential, Operation, Preview, _hash, _preview_material

class ControlEvidenceMixin:
    def _transport(
        self,
        kind: str,
        connection: Connection,
        credential: EphemeralCredential,
        **kwargs: Any,
    ) -> Any:
        return self.transport(
            kind,
            connection=connection,
            credential=credential,
            timeout_seconds=self.policy.call_timeout_seconds,
            **kwargs,
        )

    def _assert_run_fence(
        self, preview: Preview, run_id: str, expected_fence: str
    ) -> None:
        current_fence = self.ledger.assert_lock(
            preview.project_id, run_id, preview.hash
        )
        if not secrets.compare_digest(current_fence, expected_fence):
            raise ControlError(
                "lock_lost",
                "/locks",
                "run fencing token changed during adapter work",
                run_id,
            )

    def _classify_apply_failure(self, run_id: str) -> None:
        """Give every post-begin apply exit a durable recovery state."""
        if self.ledger.state(run_id) != "applying":
            return
        state = (
            "outcome_ambiguous"
            if self.ledger.unresolved_intents(run_id)
            else "partially_applied"
        )
        self.ledger.set_state(run_id, state)
        self.session_state = state

    def _reauthorize(
        self, operation: Operation, fencing_token: str | None = None
    ) -> None:
        connection, credential = self._require_connection()
        credential.reveal()
        self.policy.validate(operation, connection.permissions)
        identity = self._transport(
            "reauthorize",
            connection,
            credential,
            fencing_token=fencing_token,
        )
        if not isinstance(identity, Mapping) or not self._identity_matches_connection(
            identity, connection
        ):
            raise ControlError(
                "authorization_changed",
                "/connection",
                "tenant, actor, permission, or address binding changed",
            )

    @staticmethod
    def _identity_matches_connection(
        identity: Mapping[str, Any], connection: Connection
    ) -> bool:
        if identity.get("tenant_fingerprint") != connection.tenant_fingerprint:
            return False
        if identity.get("actor") != connection.actor:
            return False
        if tuple(sorted(identity.get("permissions", ()))) != connection.permissions:
            return False
        if tuple(sorted(identity.get("resolved_addresses", ()))) != connection.pinned_addresses:
            return False
        if identity.get("canonical_origin") != connection.origin:
            return False
        if identity.get("version") != connection.version:
            return False
        return True

    def _require_connection(self) -> tuple[Connection, EphemeralCredential]:
        if not self.connection or not self._credential:
            raise ControlError(
                "disconnected", "/connection", "session connection is required"
            )
        self._credential.reveal()
        return self.connection, self._credential

    def _valid_preview(self, baseline: Any, project: Any) -> Preview:
        connection, _ = self._require_connection()
        preview = self.preview
        if not self._approved_preview_matches(preview, connection, baseline, project):
            raise ControlError(
                "approval_invalidated",
                "/apply",
                "preview approval is absent, expired, changed, or rebound",
            )
        return preview

    def _approved_preview_matches(self, preview: Preview | None, connection: Connection, baseline: Any, project: Any) -> bool:
        return bool(preview) and self._approval_material_matches(preview) and self._preview_connection_matches(preview, connection) and self._preview_inputs_match(preview, baseline, project)

    def _approval_material_matches(self, preview: Preview) -> bool:
        return bool(self._approved_hash) and preview.expires_at > time.time() and secrets.compare_digest(self._approved_hash, preview.hash) and secrets.compare_digest(preview.hash, _hash(_preview_material(preview)))

    def _preview_connection_matches(self, preview: Preview, connection: Connection) -> bool:
        return preview.connection_id == connection.id and preview.tenant_fingerprint == connection.tenant_fingerprint and preview.actor == connection.actor and preview.permissions == connection.permissions and preview.policy_hash == self.policy.digest

    @staticmethod
    def _preview_inputs_match(preview: Preview, baseline: Any, project: Any) -> bool:
        return preview.baseline_hash == _hash(baseline) and preview.project_hash == _hash(project)

    def _run_preview(self, run_id: str, allowed_states: set[str]) -> Preview:
        connection, _ = self._require_connection()
        run = self.ledger.run(run_id)
        preview = self.preview
        if not self._run_preview_matches(run, preview, connection, allowed_states):
            raise ControlError("run_invalid", "/runs", "run is not bound to this preview, tenant, and state", run_id)
        if not self._run_evidence_matches(preview, run_id):
            raise ControlError("ledger_integrity", "/ledger", "authenticated operational evidence does not match the protected preview", run_id)
        return preview

    def _run_preview_matches(self, run: Mapping[str, Any] | None, preview: Preview | None, connection: Connection, allowed_states: set[str]) -> bool:
        return bool(run) and bool(preview) and run["state"] in allowed_states and self._run_preview_binding_matches(run, preview, connection)

    def _run_preview_binding_matches(self, run: Mapping[str, Any], preview: Preview, connection: Connection) -> bool:
        return run["preview_hash"] == preview.hash and run["tenant_fingerprint"] == connection.tenant_fingerprint and run["project_id"] == preview.project_id and preview.hash == _hash(_preview_material(preview)) and preview.actor == connection.actor and preview.permissions == connection.permissions and preview.policy_hash == self.policy.digest

    def _run_evidence_matches(self, preview: Preview, run_id: str) -> bool:
        by_id = {operation.id: operation for operation in preview.operations}
        intent_hashes = self.ledger.intent_hashes(run_id)
        outcomes = self.ledger.outcomes(run_id)
        not_applied = self.ledger.not_applied_hashes(run_id)
        rollback_intents = self.ledger.rollback_intents(run_id)
        return self._evidence_sets_match(intent_hashes, outcomes, not_applied, rollback_intents) and self._evidence_hashes_match(by_id, intent_hashes, outcomes, not_applied, rollback_intents)

    @staticmethod
    def _evidence_sets_match(intents: Mapping[str, str], outcomes: Mapping[str, str], not_applied: Mapping[str, str], rollbacks: Mapping[str, str]) -> bool:
        return (set(outcomes) | set(not_applied) | set(rollbacks)) <= set(intents) and set(outcomes).isdisjoint(not_applied)

    @staticmethod
    def _evidence_hashes_match(by_id: Mapping[str, Operation], intents: Mapping[str, str], outcomes: Mapping[str, str], not_applied: Mapping[str, str], rollbacks: Mapping[str, str]) -> bool:
        return all((
        ControlEvidenceMixin._intent_hashes_match(by_id, intents),
        ControlEvidenceMixin._outcome_hashes_match(by_id, outcomes),
        ControlEvidenceMixin._not_applied_hashes_match(by_id, not_applied),
        ControlEvidenceMixin._rollback_hashes_match(by_id, rollbacks),
        ))

    @staticmethod
    def _intent_hashes_match(by_id: Mapping[str, Operation], values: Mapping[str, str]) -> bool:
        return all(operation_id in by_id and value == _hash(by_id[operation_id]) for operation_id, value in values.items())

    @staticmethod
    def _outcome_hashes_match(by_id: Mapping[str, Operation], values: Mapping[str, str]) -> bool:
        return all(operation_id in by_id and value == by_id[operation_id].postcondition for operation_id, value in values.items())

    @staticmethod
    def _not_applied_hashes_match(by_id: Mapping[str, Operation], values: Mapping[str, str]) -> bool:
        return all(operation_id in by_id and value == by_id[operation_id].precondition for operation_id, value in values.items())

    @staticmethod
    def _rollback_hashes_match(by_id: Mapping[str, Operation], values: Mapping[str, str]) -> bool:
        return all(operation_id in by_id and value == by_id[operation_id].rollback.get("postcondition", by_id[operation_id].precondition) for operation_id, value in values.items())
