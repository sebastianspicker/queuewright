"""Run, evidence, and recovery mixin for Ledger."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .models import ControlError, Operation, Preview, SAFE_KEY, _hash, _preview_from_bytes

class LedgerRunsMixin:
    def begin_run(
        self,
        run_id: str,
        preview_hash: str,
        tenant_fingerprint: str,
        project_id: str,
    ) -> None:
        self._begin()
        try:
            self.db.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    "applying",
                    preview_hash,
                    tenant_fingerprint,
                    project_id,
                    time.time(),
                ),
            )
            self._audit_locked(
                run_id,
                "state",
                {
                    "state": "applying",
                    "preview_hash": preview_hash,
                    "tenant_fingerprint": tenant_fingerprint,
                    "project_id": project_id,
                },
            )
            self._commit()
        except sqlite3.IntegrityError as error:
            self._rollback()
            raise ControlError(
                "run_exists", "/runs", "run ID has already been used", run_id
            ) from error
        except Exception:
            self._rollback()
            raise
    def set_state(self, run_id: str, state: str) -> None:
        self._begin()
        try:
            run = self.db.execute(
                "SELECT preview_hash,tenant_fingerprint,project_id FROM runs "
                "WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise ControlError("run_missing", "/runs", "run does not exist", run_id)
            result = self.db.execute(
                "UPDATE runs SET state=?, updated=? WHERE run_id=?",
                (state, time.time(), run_id),
            )
            if result.rowcount != 1:
                raise ControlError("run_missing", "/runs", "run does not exist", run_id)
            self._audit_locked(
                run_id,
                "state",
                {
                    "state": state,
                    "preview_hash": run[0],
                    "tenant_fingerprint": run[1],
                    "project_id": run[2],
                },
            )
            self._commit()
        except Exception:
            self._rollback()
            raise

    def run(self, run_id: str) -> dict[str, Any] | None:
        self._verify_operational_integrity()
        row = self.db.execute(
            "SELECT state,preview_hash,tenant_fingerprint,project_id,updated "
            "FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "state": row[0],
            "preview_hash": row[1],
            "tenant_fingerprint": row[2],
            "project_id": row[3],
            "updated": row[4],
        }

    def state(self, run_id: str) -> str | None:
        run = self.run(run_id)
        return str(run["state"]) if run else None

    def intent(self, run_id: str, operation: Operation) -> None:
        self._begin()
        try:
            operation_hash = _hash(operation)
            self.db.execute(
                "INSERT INTO intents VALUES (?, ?, ?, ?)",
                (run_id, operation.id, operation_hash, time.time()),
            )
            self._audit_locked(
                run_id,
                "intent",
                {
                    "operation_id": operation.id,
                    "operation_hash": operation_hash,
                },
            )
            self._commit()
        except sqlite3.IntegrityError as error:
            self._rollback()
            raise ControlError(
                "intent_exists",
                "/apply",
                "operation intent already exists",
                run_id,
            ) from error
        except Exception:
            self._rollback()
            raise

    def outcome(self, run_id: str, operation_id: str, postimage_hash: str) -> None:
        self._begin()
        try:
            self.db.execute(
                "INSERT INTO outcomes VALUES (?, ?, ?, ?, ?)",
                (run_id, operation_id, postimage_hash, "applied", time.time()),
            )
            self._audit_locked(
                run_id,
                "operation_applied",
                {"operation_id": operation_id, "postimage_hash": postimage_hash},
            )
            self._commit()
        except Exception:
            self._rollback()
            raise

    def outcomes(self, run_id: str) -> dict[str, str]:
        self._verify_operational_integrity()
        return {
            operation_id: postimage_hash
            for operation_id, postimage_hash in self.db.execute(
                "SELECT operation_id,postimage_hash FROM outcomes "
                "WHERE run_id=? AND state='applied'",
                (run_id,),
            )
        }

    def intent_hashes(self, run_id: str) -> dict[str, str]:
        self._verify_operational_integrity()
        return {
            operation_id: operation_hash
            for operation_id, operation_hash in self.db.execute(
                "SELECT operation_id,operation_hash FROM intents WHERE run_id=?",
                (run_id,),
            )
        }

    def intents(self, run_id: str) -> set[str]:
        return set(self.intent_hashes(run_id))

    def resolve_not_applied(
        self, run_id: str, operation_id: str, proven_hash: str
    ) -> None:
        self._begin()
        try:
            if self.db.execute(
                "SELECT 1 FROM intents WHERE run_id=? AND operation_id=?",
                (run_id, operation_id),
            ).fetchone() is None:
                raise ControlError(
                    "intent_missing",
                    "/reconcile",
                    "operation has no durable intent",
                    run_id,
                )
            self.db.execute(
                "INSERT INTO intent_resolutions VALUES (?, ?, 'not_applied', ?, ?)",
                (run_id, operation_id, proven_hash, time.time()),
            )
            self._audit_locked(
                run_id,
                "operation_not_applied",
                {"operation_id": operation_id, "proven_hash": proven_hash},
            )
            self._commit()
        except sqlite3.IntegrityError as error:
            self._rollback()
            raise ControlError(
                "intent_resolved",
                "/reconcile",
                "operation intent was already resolved",
                run_id,
            ) from error
        except Exception:
            self._rollback()
            raise

    def not_applied_hashes(self, run_id: str) -> dict[str, str]:
        self._verify_operational_integrity()
        return {
            operation_id: proven_hash
            for operation_id, proven_hash in self.db.execute(
                "SELECT operation_id,proven_hash FROM intent_resolutions "
                "WHERE run_id=? AND resolution='not_applied'",
                (run_id,),
            )
        }

    def not_applied(self, run_id: str) -> set[str]:
        return set(self.not_applied_hashes(run_id))

    def unresolved_intents(self, run_id: str) -> set[str]:
        return self.intents(run_id) - set(self.outcomes(run_id)) - self.not_applied(run_id)

    def mark_rolled_back(self, run_id: str, operation_id: str) -> None:
        self._begin()
        try:
            result = self.db.execute(
                "UPDATE outcomes SET state='rolled_back' "
                "WHERE run_id=? AND operation_id=? AND state='applied'",
                (run_id, operation_id),
            )
            if result.rowcount != 1:
                raise ControlError(
                    "rollback_invalid",
                    "/rollback",
                    "operation was not applied by this run",
                    run_id,
                )
            self._audit_locked(
                run_id, "operation_rolled_back", {"operation_id": operation_id}
            )
            self._commit()
        except Exception:
            self._rollback()
            raise

    def rollback_intent(
        self, run_id: str, operation_id: str, expected_hash: str
    ) -> None:
        self._begin()
        try:
            result = self.db.execute(
                "INSERT OR IGNORE INTO rollback_intents VALUES (?, ?, ?, ?)",
                (run_id, operation_id, expected_hash, time.time()),
            )
            if result.rowcount == 1:
                self._audit_locked(
                    run_id,
                    "rollback_intent",
                    {"operation_id": operation_id, "expected_hash": expected_hash},
                )
            self._commit()
        except Exception:
            self._rollback()
            raise

    def rollback_intents(self, run_id: str) -> dict[str, str]:
        self._verify_operational_integrity()
        return {
            operation_id: expected_hash
            for operation_id, expected_hash in self.db.execute(
                "SELECT operation_id,expected_hash FROM rollback_intents WHERE run_id=?",
                (run_id,),
            )
        }

    def put_blob(self, name: str, value: bytes, run_id: str = "system") -> None:
        if SAFE_KEY.fullmatch(name) is None:
            raise ControlError("evidence_invalid", "/ledger/blobs", "invalid blob name")
        nonce = secrets.token_bytes(12)
        ciphertext = nonce + AESGCM(self._key).encrypt(nonce, value, name.encode())
        self._begin()
        try:
            replaced = self.db.execute(
                "SELECT 1 FROM blobs WHERE name=?", (name,)
            ).fetchone() is not None
            self.db.execute(
                "INSERT INTO blobs VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET "
                "ciphertext=excluded.ciphertext, created=excluded.created",
                (name, ciphertext, time.time()),
            )
            self._audit_locked(
                run_id,
                "evidence_replaced" if replaced else "evidence_stored",
                {"name_hash": hashlib.sha256(name.encode()).hexdigest()},
            )
            self._commit()
        except Exception:
            self._rollback()
            raise

    def get_blob(self, name: str) -> bytes | None:
        row = self.db.execute(
            "SELECT ciphertext FROM blobs WHERE name=?", (name,)
        ).fetchone()
        if not row:
            return None
        value = row[0]
        return AESGCM(self._key).decrypt(value[:12], value[12:], name.encode())

    def load_preview(self, preview_hash: str) -> Preview:
        value = self.get_blob(f"preview:{preview_hash}")
        if value is None:
            raise ControlError(
                "preview_missing", "/ledger/blobs", "stored preview is unavailable"
            )
        return _preview_from_bytes(value)

    def incomplete_runs(self) -> list[dict[str, Any]]:
        self._verify_operational_integrity()
        terminal = ("verified", "rolled_back")
        return [
            {
                "run_id": row[0],
                "state": row[1],
                "preview_hash": row[2],
                "tenant_fingerprint": row[3],
                "project_id": row[4],
                "updated": row[5],
            }
            for row in self.db.execute(
                "SELECT run_id,state,preview_hash,tenant_fingerprint,project_id,updated "
                "FROM runs WHERE state NOT IN (?, ?) ORDER BY updated",
                terminal,
            )
        ]

    def purge_evidence(self, before: float | None = None) -> int:
        cutoff = before if before is not None else time.time() - 90 * 86400
        self._begin()
        try:
            result = self.db.execute(
                "DELETE FROM blobs WHERE created < ? AND name NOT IN ("
                "SELECT 'preview:' || preview_hash FROM runs "
                "WHERE state NOT IN ('verified', 'rolled_back'))",
                (cutoff,),
            )
            self._audit_locked(
                "system", "evidence_purged", {"count": result.rowcount}
            )
            self._commit()
            return result.rowcount
        except Exception:
            self._rollback()
            raise
