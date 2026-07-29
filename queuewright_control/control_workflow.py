"""Preview approval and apply workflow mixin."""

from __future__ import annotations

import secrets
import time
from typing import Any, Mapping, Sequence

from .models import (
    Connection, ControlError, EphemeralCredential, Operation, Preview, SAFE_KEY,
    WRITE_METHODS, _canonical_bytes, _hash, _preview_material, _topological_operations,
)

class ControlWorkflowMixin:
    def make_preview(
        self,
        baseline: Any,
        project: Any,
        operations: Sequence[Operation],
        rollback_limitations: Sequence[str] = (),
        *,
        project_id: str = "project",
        ttl_seconds: int = 600,
    ) -> Preview:
        connection, _ = self._require_connection()
        if SAFE_KEY.fullmatch(project_id) is None:
            raise ControlError(
                "preview_invalid", "/preview/project_id", "safe project ID required"
            )
        ordered = _topological_operations(operations)
        for operation in ordered:
            self.policy.validate(operation, connection.permissions)
        if not all(isinstance(item, str) for item in rollback_limitations):
            raise ControlError(
                "preview_invalid",
                "/preview/rollback_limitations",
                "rollback limitations must be text",
            )
        material = {
            "connection_id": connection.id,
            "tenant_fingerprint": connection.tenant_fingerprint,
            "actor": connection.actor,
            "permissions": connection.permissions,
            "baseline_hash": _hash(baseline),
            "project_hash": _hash(project),
            "project_id": project_id,
            "policy_version": self.policy.version,
            "policy_hash": self.policy.digest,
            "operations": ordered,
            "rollback_limitations": tuple(rollback_limitations),
            "nonce": secrets.token_urlsafe(24),
            "expires_at": time.time() + ttl_seconds,
        }
        preview = Preview(**material, hash=_hash(material))
        self.preview = preview
        self._approved_hash = None
        self.session_state = "previewed"
        self.ledger.put_blob(
            f"preview:{preview.hash}", _canonical_bytes(preview), "preview"
        )
        return preview

    def approve(self, preview_hash: str) -> None:
        preview = self.preview
        if (
            not preview
            or preview.expires_at <= time.time()
            or not secrets.compare_digest(preview.hash, preview_hash)
            or not secrets.compare_digest(preview.hash, _hash(_preview_material(preview)))
        ):
            raise ControlError(
                "preview_invalid", "/approval", "preview is absent, expired, or changed"
            )
        self._approved_hash = preview_hash
        self.session_state = "approved"

    def apply(self, run_id: str, baseline: Any, project: Any) -> None:
        preview = self._valid_preview(baseline, project)
        connection, credential = self._require_connection()
        fence = self._begin_apply_run(preview, connection, run_id)
        self.session_state = "applying"
        for operation in preview.operations:
            fence = self._apply_operation(preview, connection, credential, run_id, operation, fence)
        self._finish_apply_run(preview, run_id, fence)

    def _begin_apply_run(self, preview: Preview, connection: Connection, run_id: str) -> str:
        if SAFE_KEY.fullmatch(run_id) is None:
            raise ControlError("run_invalid", "/runs", "safe run ID required")
        self._approved_hash = None  # one-time approval is consumed before mutation.
        fence = self.ledger.acquire_lock(
            preview.project_id,
            run_id,
            preview.hash,
            self.policy.lease_seconds,
        )
        try:
            self.ledger.begin_run(
                run_id,
                preview.hash,
                connection.tenant_fingerprint,
                preview.project_id,
            )
        except Exception:
            self.ledger.release_lock(preview.project_id, run_id, preview.hash)
            raise
        return fence

    def _apply_operation(self, preview: Preview, connection: Connection, credential: EphemeralCredential, run_id: str, operation: Operation, fence: str) -> str:
        try:
            return self._execute_operation(preview, connection, credential, run_id, operation, fence)
        except ControlError:
            self._classify_apply_failure(run_id)
            raise
        except Exception as error:
            self._classify_apply_failure(run_id)
            raise ControlError("transport_failed", "/apply", "adapter failed; reconciliation is required", run_id) from error

    def _execute_operation(self, preview: Preview, connection: Connection, credential: EphemeralCredential, run_id: str, operation: Operation, fence: str) -> str:
        try:
                fence = self._prepare_operation(preview, connection, credential, run_id, operation, fence)
                self._write_operation(preview, connection, credential, run_id, operation, fence)
                self._record_operation_outcome(preview, connection, credential, run_id, operation, fence)
                return fence
        except Exception:
            raise

    def _prepare_operation(self, preview: Preview, connection: Connection, credential: EphemeralCredential, run_id: str, operation: Operation, fence: str) -> str:
        try:
                fence = self.ledger.ensure_lock(
                    preview.project_id,
                    run_id,
                    preview.hash,
                    self.policy.lease_seconds,
                )
                self._reauthorize(operation, fence)
                self._assert_run_fence(preview, run_id, fence)
                preimage = self._transport(
                    "precondition",
                    connection,
                    credential,
                    operation=operation,
                    fencing_token=fence,
                )
                self._assert_run_fence(preview, run_id, fence)
                if not isinstance(preimage, Mapping) or preimage.get("hash") != operation.precondition:
                    self.ledger.set_state(run_id, "drift_detected")
                    self.session_state = "drift_detected"
                    raise ControlError(
                        "precondition_failed",
                        "/apply",
                        "fresh precondition does not match the approved baseline",
                        run_id,
                    )
                self.ledger.intent(run_id, operation)
                return fence
        except Exception:
            raise

    def _write_operation(self, preview: Preview, connection: Connection, credential: EphemeralCredential, run_id: str, operation: Operation, fence: str) -> None:
        try:
                started = time.monotonic()
                response = self._transport(
                    "write",
                    connection,
                    credential,
                    operation=operation,
                    fencing_token=fence,
                )
                self._require_write_fence(preview, run_id, fence, started)
                self._reconcile_ambiguous_write(preview, connection, credential, run_id, operation, fence, response)
        except Exception:
            raise

    def _require_write_fence(self, preview: Preview, run_id: str, fence: str, started: float) -> None:
        try:
            current_fence = self.ledger.assert_lock(preview.project_id, run_id, preview.hash)
        except ControlError:
            current_fence = None
        if time.monotonic() - started > self.policy.call_timeout_seconds or current_fence != fence:
            self.ledger.set_state(run_id, "outcome_ambiguous")
            self.session_state = "outcome_ambiguous"
            raise ControlError("outcome_ambiguous", "/apply", "write exceeded its approved time or fencing boundary", run_id)

    def _reconcile_ambiguous_write(self, preview: Preview, connection: Connection, credential: EphemeralCredential, run_id: str, operation: Operation, fence: str, response: Any) -> None:
        if operation.method not in WRITE_METHODS or isinstance(response, Mapping) and response.get("ambiguous") is not True:
            return
        self.ledger.set_state(run_id, "outcome_ambiguous")
        self.session_state = "outcome_ambiguous"
        result = self._transport("reconcile", connection, credential, operation=operation, fencing_token=fence)
        self._assert_run_fence(preview, run_id, fence)
        if not isinstance(result, Mapping) or result.get("matched") is not True:
            raise ControlError("outcome_ambiguous", "/apply", "write outcome could not be reconciled", run_id)

    def _record_operation_outcome(self, preview: Preview, connection: Connection, credential: EphemeralCredential, run_id: str, operation: Operation, fence: str) -> None:
        try:
                readback = self._transport(
                    "readback",
                    connection,
                    credential,
                    operation=operation,
                    fencing_token=fence,
                )
                self._assert_run_fence(preview, run_id, fence)
                if not isinstance(readback, Mapping) or readback.get("hash") != operation.postcondition:
                    self.ledger.set_state(run_id, "outcome_ambiguous")
                    self.session_state = "outcome_ambiguous"
                    raise ControlError(
                        "readback_failed",
                        "/apply",
                        "authoritative readback does not match the approved postcondition",
                        run_id,
                    )
                self.ledger.outcome(run_id, operation.id, operation.postcondition)
        except Exception:
            raise
        return fence

    def _finish_apply_run(self, preview: Preview, run_id: str, fence: str) -> None:
        try:
            self._assert_run_fence(preview, run_id, fence)
            self.ledger.set_state(run_id, "applied")
        except ControlError:
            self._classify_apply_failure(run_id)
            raise
        self.session_state = "applied"
