"""Owner-private encrypted SQLite ledger."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from .ledger_audit import LedgerAuditMixin
from .ledger_locks import LedgerLockMixin
from .ledger_runs import LedgerRunsMixin
from .models import LEDGER_SCHEMA, ControlError, MasterKeyProvider, OperationalFacts

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - unsupported installation only
    AESGCM = None  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class _DatabaseStamp:
    data_version: int
    total_changes: int
    schema_version: int
    temporary_schema_version: int
    foreign_keys: int
    journal_mode: str
    synchronous: int
    file: tuple[int, int, int, int, int] | None


@dataclass
class _VerifiedState:
    head: tuple[int, str] | None
    facts: OperationalFacts
    stamp: _DatabaseStamp
    standard_schema: bool


@dataclass
class _TransactionState:
    base: _VerifiedState
    begin_stamp: _DatabaseStamp
    head: tuple[int, str] | None
    audit_entries: int
    deltas: OperationalFacts


class Ledger(LedgerAuditMixin, LedgerRunsMixin, LedgerLockMixin):
    _STANDARD_TABLES: ClassVar[frozenset[str]] = frozenset({
        "audit",
        "blobs",
        "intent_resolutions",
        "intents",
        "locks",
        "outcomes",
        "rollback_intents",
        "runs",
    })

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
        self._audit_key = hashlib.sha256(
            self._key + b"queuewright-control-audit"
        ).digest()
        self._cache: _VerifiedState | None = None
        self._transaction: _TransactionState | None = None
        self._path_identity: tuple[int, int] | None = None
        self._standard_schema_signature = self._pristine_schema_signature()
        self._prepare_path(Path(self.path))
        self.db = self._open_database()
        self._expected_journal_mode = str(
            self.db.execute("PRAGMA journal_mode").fetchone()[0]
        ).lower()
        self._remember_path_identity()
        self._initialize_verified_state()

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
        if (
            stat.S_ISLNK(details.st_mode)
            or not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.geteuid()
        ):
            raise ControlError(
                "ledger_unsafe", "/ledger", "ledger must be an owner-controlled regular file"
            )
        os.chmod(path, 0o600)

    @staticmethod
    def _create_private_path(path: Path) -> None:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        os.close(descriptor)

    def _remember_path_identity(self) -> None:
        if self.path == ":memory:":
            return
        details = os.lstat(self.path)
        self._path_identity = (details.st_dev, details.st_ino)
        self._validated_file_stamp()

    def _validated_file_stamp(self) -> tuple[int, int, int, int, int] | None:
        if self.path == ":memory:":
            return None
        try:
            details = os.lstat(self.path)
        except OSError as error:
            raise ControlError(
                "ledger_unsafe", "/ledger", "ledger path is unavailable"
            ) from error
        identity = (details.st_dev, details.st_ino)
        if (
            stat.S_ISLNK(details.st_mode)
            or not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.geteuid()
            or stat.S_IMODE(details.st_mode) != 0o600
            or (self._path_identity is not None and identity != self._path_identity)
        ):
            raise ControlError(
                "ledger_unsafe",
                "/ledger",
                "ledger path identity, ownership, or mode changed",
            )
        return (
            details.st_dev,
            details.st_ino,
            details.st_size,
            details.st_mtime_ns,
            details.st_ctime_ns,
        )

    def _database_stamp(self) -> _DatabaseStamp:
        foreign_keys, journal_mode, synchronous = self._connection_settings()
        if (
            foreign_keys != 1
            or journal_mode != self._expected_journal_mode
            or synchronous != 2
        ):
            raise ControlError(
                "ledger_unsafe",
                "/ledger",
                "ledger connection safety settings changed",
            )
        return _DatabaseStamp(
            int(self.db.execute("PRAGMA data_version").fetchone()[0]),
            int(self.db.total_changes),
            int(self.db.execute("PRAGMA schema_version").fetchone()[0]),
            int(self.db.execute("PRAGMA temp.schema_version").fetchone()[0]),
            foreign_keys,
            journal_mode,
            synchronous,
            self._validated_file_stamp(),
        )

    def _connection_settings(self) -> tuple[int, str, int]:
        return (
            int(self.db.execute("PRAGMA foreign_keys").fetchone()[0]),
            str(self.db.execute("PRAGMA journal_mode").fetchone()[0]).lower(),
            int(self.db.execute("PRAGMA synchronous").fetchone()[0]),
        )

    @staticmethod
    def _schema_signature(database: sqlite3.Connection, schema: str) -> tuple[Any, ...]:
        return tuple(
            database.execute(
                f"SELECT type,name,tbl_name,sql FROM {schema}.sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            )
        )

    @classmethod
    def _pristine_schema_signature(cls) -> tuple[Any, ...]:
        pristine = sqlite3.connect(":memory:")
        try:
            pristine.executescript(LEDGER_SCHEMA)
            return cls._schema_signature(pristine, "main")
        finally:
            pristine.close()

    def _has_standard_schema(self) -> bool:
        return (
            self._schema_signature(self.db, "main") == self._standard_schema_signature
            and not self._schema_signature(self.db, "temp")
        )

    def _initialize_verified_state(self) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            state = self._full_verified_state()
            state.stamp = self._database_stamp()
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            self._invalidate_cache()
            self.db.close()
            raise
        self._cache = state

    def close(self) -> None:
        self._invalidate_cache()
        self.db.close()

    def _invalidate_cache(self) -> None:
        self._cache = None
        self._transaction = None

    @staticmethod
    def _empty_deltas() -> OperationalFacts:
        return OperationalFacts({}, {}, {}, {}, {})

    @staticmethod
    def _new_verified_state(
        head: tuple[int, str] | None,
        facts: OperationalFacts,
        stamp: _DatabaseStamp,
        standard_schema: bool,
    ) -> _VerifiedState:
        return _VerifiedState(head, facts, stamp, standard_schema)

    def _cache_is_current(self, stamp: _DatabaseStamp) -> bool:
        state = self._cache
        return bool(
            state is not None
            and state.standard_schema
            and state.stamp == stamp
            and self._key_provider.get_audit_anchor() == state.head
        )

    def _ensure_verified_state(self) -> _VerifiedState:
        stamp = self._database_stamp()
        if self._cache_is_current(stamp):
            assert self._cache is not None
            return self._cache
        state = self._full_verified_state()
        state.stamp = self._database_stamp()
        self._cache = state
        return state

    def _begin(self) -> None:
        if self._transaction is not None or self.db.in_transaction:
            self._invalidate_cache()
            raise ControlError(
                "ledger_integrity", "/ledger", "nested or untrusted ledger transaction"
            )
        self.db.execute("BEGIN IMMEDIATE")
        try:
            base = self._ensure_verified_state()
            begin_stamp = self._database_stamp()
            self._transaction = _TransactionState(
                base, begin_stamp, base.head, 0, self._empty_deltas()
            )
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            self._invalidate_cache()
            raise

    def _commit(self) -> None:
        transaction = self._transaction
        if transaction is None or not self.db.in_transaction:
            self._invalidate_cache()
            raise ControlError(
                "ledger_integrity", "/ledger", "trusted ledger transaction is unavailable"
            )
        try:
            self._verify_transaction(transaction)
        except Exception:
            self.db.execute("ROLLBACK")
            self._invalidate_cache()
            raise

        self.db.execute("COMMIT")
        self._transaction = None
        self._cache = None
        try:
            self._reconcile_committed_transaction(transaction)
        except Exception:
            self._invalidate_cache()
            raise

    def _verify_transaction(self, transaction: _TransactionState) -> None:
        tail = self.db.execute(
            "SELECT sequence,entry_mac FROM audit ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        actual_head = (int(tail[0]), str(tail[1])) if tail else None
        if actual_head != transaction.head:
            raise ControlError(
                "ledger_integrity", "/ledger/audit", "audit tail changed during transaction"
            )
        base_sequence = transaction.base.head[0] if transaction.base.head else 0
        appended = int(
            self.db.execute(
                "SELECT COUNT(*) FROM audit WHERE sequence>?", (base_sequence,)
            ).fetchone()[0]
        )
        if appended != transaction.audit_entries:
            raise ControlError(
                "ledger_integrity", "/ledger/audit", "audit transaction shape is invalid"
            )
        if transaction.base.standard_schema:
            self._verify_operational_deltas(transaction)
            return
        # Custom schema, especially triggers, can mutate rows outside the keys
        # touched by this transaction. It therefore never uses the delta fast path.
        self._full_verified_state(advance_anchor=False)

    def _reconcile_committed_transaction(self, transaction: _TransactionState) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            stamp = self._database_stamp()
            tail = self.db.execute(
                "SELECT sequence,entry_mac FROM audit ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            actual_head = (int(tail[0]), str(tail[1])) if tail else None
            concurrent_change = (
                actual_head != transaction.head
                or stamp.data_version != transaction.begin_stamp.data_version
                or stamp.schema_version != transaction.begin_stamp.schema_version
                or stamp.temporary_schema_version
                != transaction.begin_stamp.temporary_schema_version
                or not self._has_standard_schema()
            )
            if concurrent_change:
                state = self._full_verified_state()
            else:
                anchor = self._key_provider.get_audit_anchor()
                if anchor not in {transaction.base.head, transaction.head}:
                    state = self._full_verified_state()
                else:
                    if transaction.head is not None and anchor != transaction.head:
                        self._advance_anchor(anchor, transaction.head)
                    self._promote_deltas(transaction.base.facts, transaction.deltas)
                    state = _VerifiedState(
                        transaction.head,
                        transaction.base.facts,
                        stamp,
                        transaction.base.standard_schema,
                    )
            state.stamp = self._database_stamp()
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        self._cache = state

    def _rollback(self) -> None:
        if self.db.in_transaction:
            self.db.execute("ROLLBACK")
        self._invalidate_cache()

    @staticmethod
    def _promote_deltas(base: OperationalFacts, deltas: OperationalFacts) -> None:
        base.runs.update(deltas.runs)
        base.intents.update(deltas.intents)
        base.outcomes.update(deltas.outcomes)
        base.resolutions.update(deltas.resolutions)
        base.rollbacks.update(deltas.rollbacks)

    def _verified_rows(
        self, query: str, parameters: tuple[Any, ...] = ()
    ) -> list[tuple[Any, ...]]:
        if self._transaction is not None:
            return list(self.db.execute(query, parameters))
        if self.db.in_transaction:
            self._invalidate_cache()
            raise ControlError(
                "ledger_integrity", "/ledger", "untrusted ledger transaction"
            )
        self.db.execute("BEGIN")
        try:
            self.db.execute("SELECT 1 FROM main.sqlite_schema LIMIT 1").fetchone()
            self._ensure_verified_state()
            rows = list(self.db.execute(query, parameters))
            self.db.execute("COMMIT")
            return rows
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            self._invalidate_cache()
            raise
