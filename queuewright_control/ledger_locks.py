"""Project lock and fencing mixin for Ledger."""

from __future__ import annotations

import secrets
import sqlite3
import time

from .models import ControlError, _hash

class LedgerLockMixin:
    def acquire_lock(
        self,
        project: str,
        owner: str,
        preview_hash: str,
        lease_seconds: int = 900,
    ) -> str:
        now = time.time()
        fence = secrets.token_urlsafe(24)
        self._begin()
        try:
            blocking = self.db.execute(
                "SELECT run_id,state FROM runs WHERE project_id=? "
                "AND state NOT IN ('verified','rolled_back') AND run_id<>? "
                "ORDER BY updated LIMIT 1",
                (project, owner),
            ).fetchone()
            if blocking:
                raise ControlError(
                    "run_recovery_required",
                    "/locks",
                    "an incomplete run must be recovered before this project can change again",
                    str(blocking[0]),
                )
            self.db.execute("DELETE FROM locks WHERE expires < ?", (now,))
            self.db.execute(
                "INSERT INTO locks VALUES (?, ?, ?, ?, ?, ?)",
                (project, owner, preview_hash, fence, now + lease_seconds, now),
            )
            self._audit_locked(
                owner,
                "lock_acquired",
                {"project_hash": _hash(project), "preview_hash": preview_hash},
            )
            self._commit()
            return fence
        except sqlite3.IntegrityError as error:
            self._rollback()
            raise ControlError("lock_held", "/locks", "project is already locked") from error
        except Exception:
            self._rollback()
            raise

    def assert_lock(self, project: str, owner: str, preview_hash: str) -> str:
        row = self.db.execute(
            "SELECT owner,preview_hash,fence,expires FROM locks WHERE project=?", (project,)
        ).fetchone()
        if (
            not row
            or row[0] != owner
            or row[1] != preview_hash
            or row[3] <= time.time()
        ):
            raise ControlError("lock_lost", "/locks", "run no longer owns the lock", owner)
        return str(row[2])

    def renew_lock(
        self,
        project: str,
        owner: str,
        preview_hash: str,
        lease_seconds: int = 900,
    ) -> str:
        self._begin()
        try:
            result = self.db.execute(
                "UPDATE locks SET expires=? WHERE project=? AND owner=? "
                "AND preview_hash=? AND expires>?",
                (
                    time.time() + lease_seconds,
                    project,
                    owner,
                    preview_hash,
                    time.time(),
                ),
            )
            if result.rowcount != 1:
                raise ControlError(
                    "lock_lost", "/locks", "run no longer owns the lock", owner
                )
            fence = self.db.execute(
                "SELECT fence FROM locks WHERE project=?", (project,)
            ).fetchone()[0]
            self._commit()
            return str(fence)
        except Exception:
            self._rollback()
            raise

    def ensure_lock(
        self,
        project: str,
        owner: str,
        preview_hash: str,
        lease_seconds: int = 900,
    ) -> str:
        """Renew this run's lease or safely reacquire it after expiry."""
        now = time.time()
        self._begin()
        try:
            row = self.db.execute(
                "SELECT owner,preview_hash,fence,expires FROM locks WHERE project=?",
                (project,),
            ).fetchone()
            if row and row[3] > now:
                if row[0] != owner or row[1] != preview_hash:
                    raise ControlError(
                        "lock_held", "/locks", "project has a competing live lease"
                    )
                self.db.execute(
                    "UPDATE locks SET expires=? WHERE project=?",
                    (now + lease_seconds, project),
                )
                fence = str(row[2])
            else:
                self.db.execute("DELETE FROM locks WHERE project=?", (project,))
                fence = secrets.token_urlsafe(24)
                self.db.execute(
                    "INSERT INTO locks VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        project,
                        owner,
                        preview_hash,
                        fence,
                        now + lease_seconds,
                        now,
                    ),
                )
                self._audit_locked(
                    owner,
                    "lock_reacquired",
                    {"project_hash": _hash(project), "preview_hash": preview_hash},
                )
            self._commit()
            return fence
        except Exception:
            self._rollback()
            raise

    def release_lock(self, project: str, owner: str, preview_hash: str) -> None:
        self._begin()
        try:
            result = self.db.execute(
                "DELETE FROM locks WHERE project=? AND owner=? AND preview_hash=?",
                (project, owner, preview_hash),
            )
            if result.rowcount != 1:
                raise ControlError(
                    "lock_lost", "/locks", "lock ownership does not match", owner
                )
            self._audit_locked(
                owner, "lock_released", {"project_hash": _hash(project)}
            )
            self._commit()
        except Exception:
            self._rollback()
            raise
