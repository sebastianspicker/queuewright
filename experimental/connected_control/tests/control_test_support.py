"""Reusable transport doubles for connected-control contract tests."""

from __future__ import annotations

from queuewright_control import InMemoryKeyProvider, Operation

BOOTSTRAP = "launcher-only-bootstrap-capability-1234567890"


class FakeTransport:
    """Deterministic transport double with explicit recovery modes."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.ambiguous = False
        self.bad_readback = False
        self.rollback_applied_then_raises = False
        self.authorization_changes_after_writes = False
        self.write_raises_before_mutation = False
        self.reconcile_not_applied = False
        self.current_hashes: dict[str, str] = {}
        self.identity = {
            "canonical_origin": "https://tenant.example",
            "tenant_fingerprint": "tenant-fingerprint",
            "actor": "studio-service-user",
            "permissions": ["admin.group"],
            "version": "6.4",
            "resolved_addresses": ["93.184.216.34"],
            "redirected": False,
        }

    def __call__(self, kind: str, **kwargs: object) -> dict[str, object]:
        self.calls.append((kind, kwargs))
        if kind == "identity":
            return dict(self.identity)
        if kind == "reauthorize":
            return self._reauthorization_response()
        operation = kwargs.get("operation")
        if not isinstance(operation, Operation):
            return {}
        return self._operation_response(kind, operation)

    def _reauthorization_response(self) -> dict[str, object]:
        actor = self.identity["actor"]
        if self.authorization_changes_after_writes and self._has_write_call():
            actor = "changed-actor"
        return {
            "tenant_fingerprint": self.identity["tenant_fingerprint"],
            "actor": actor,
            "permissions": self.identity["permissions"],
            "resolved_addresses": self.identity["resolved_addresses"],
            "canonical_origin": self.identity["canonical_origin"],
            "version": self.identity["version"],
        }

    def _has_write_call(self) -> bool:
        return any(call_kind == "write" for call_kind, _ in self.calls[:-1])

    def _operation_response(self, kind: str, operation: Operation) -> dict[str, object]:
        if kind == "precondition":
            return {"hash": operation.precondition}
        if kind == "write":
            return self._write_response()
        if kind == "reconcile":
            return self._reconciliation_response(operation)
        if kind == "readback" and self.bad_readback:
            return {"hash": "unexpected-state"}
        if kind == "current_hash":
            return {"hash": self.current_hashes.get(operation.id, operation.postcondition)}
        if kind in {"readback", "verify"}:
            return {"hash": operation.postcondition}
        if kind == "rollback":
            return self._rollback_response(operation)
        return {}

    def _write_response(self) -> dict[str, object]:
        if self.write_raises_before_mutation:
            self.write_raises_before_mutation = False
            raise TimeoutError("write failed before remote mutation")
        return {"ambiguous": self.ambiguous}

    def _reconciliation_response(self, operation: Operation) -> dict[str, object]:
        if self.reconcile_not_applied:
            return {"matched": False, "hash": operation.precondition}
        return {"matched": True, "hash": operation.postcondition}

    def _rollback_response(self, operation: Operation) -> dict[str, object]:
        expected = str(operation.rollback.get("postcondition", operation.precondition))
        self.current_hashes[operation.id] = expected
        if self.rollback_applied_then_raises:
            self.rollback_applied_then_raises = False
            raise TimeoutError("response lost after rollback")
        return {"hash": expected}


class FlakyAnchorProvider(InMemoryKeyProvider):
    """Anchor provider that fails a configured number of compare-and-set calls."""

    def __init__(self, key: bytes) -> None:
        super().__init__(key)
        self.fail_updates = 0

    def compare_and_set_audit_anchor(
        self,
        expected: tuple[int, str] | None,
        replacement: tuple[int, str],
    ) -> bool:
        if self.fail_updates:
            self.fail_updates -= 1
            return False
        return super().compare_and_set_audit_anchor(expected, replacement)
