"""Owner-private encrypted SQLite ledger."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from pathlib import Path
from .ledger_audit import LedgerAuditMixin
from .ledger_locks import LedgerLockMixin
from .ledger_runs import LedgerRunsMixin
from .models import ControlError, LEDGER_SCHEMA, MasterKeyProvider

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - unsupported installation only
    AESGCM = None  # type: ignore[assignment,misc]

class Ledger(LedgerAuditMixin, LedgerRunsMixin, LedgerLockMixin):
    def __init__(self, path: str | Path, key_provider: MasterKeyProvider) -> None:
        if AESGCM is None:
            raise ControlError(
                "encryption_unavailable", "/ledger", "AES-GCM support is unavailable"
            )
        self.path = str(path)
        self._key_provider = key_provider
        self._key = key_provider.get_key()
        if len(self._key) not in (16, 24, 32):
            raise ControlError(
                "invalid_key", "/ledger/key", "AES-GCM key must be 128, 192, or 256 bits"
            )
        self._audit_key = hashlib.sha256(self._key + b"queuewright-control-audit").digest()
        self._prepare_path(Path(self.path))
        self.db = self._open_database()
        self._synchronize_anchor()
        self._verify_operational_integrity()

    def _open_database(self) -> sqlite3.Connection:
        database = sqlite3.connect(self.path, isolation_level=None)
        database.execute("PRAGMA journal_mode=DELETE")
        database.execute("PRAGMA synchronous=FULL")
        database.execute("PRAGMA foreign_keys=ON")
        database.executescript(LEDGER_SCHEMA)
        if self.path != ":memory:":
            os.chmod(self.path, 0o600)
        return database

    @staticmethod
    def _prepare_path(path: Path) -> None:
        if str(path) == ":memory:":
            return
        parent = path.parent
        Ledger._prepare_parent(parent)
        if path.exists() or path.is_symlink():
            Ledger._secure_existing_path(path)
            return
        Ledger._create_private_path(path)

    @staticmethod
    def _prepare_parent(parent: Path) -> None:
        if not parent.exists():
            parent.mkdir(mode=0o700, parents=True)
        if parent.is_symlink() or not parent.is_dir():
            raise ControlError("ledger_unsafe", "/ledger", "ledger parent is unsafe")
        parent_details = parent.stat()
        if (
            parent_details.st_uid != os.geteuid()
            or stat.S_IMODE(parent_details.st_mode) & 0o022
        ):
            raise ControlError(
                "ledger_unsafe",
                "/ledger",
                "ledger parent must be owner-controlled and not writable by group or others",
            )
    @staticmethod
    def _secure_existing_path(path: Path) -> None:
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            raise ControlError("ledger_unsafe", "/ledger", "ledger must be a regular file")
        os.chmod(path, 0o600)

    @staticmethod
    def _create_private_path(path: Path) -> None:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        os.close(descriptor)

    def close(self) -> None:
        self.db.close()

    def _begin(self) -> None:
        self._synchronize_anchor()
        self._verify_operational_integrity()
        self.db.execute("BEGIN IMMEDIATE")

    def _commit(self) -> None:
        self.db.execute("COMMIT")
        self._synchronize_anchor()
        self._verify_operational_integrity()

    def _rollback(self) -> None:
        if self.db.in_transaction:
            self.db.execute("ROLLBACK")
