"""Credential, key-provider, and connection models."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Protocol

from .model_protocol import ControlError

class MasterKeyProvider(Protocol):
    def get_key(self) -> bytes: ...

    def get_audit_anchor(self) -> tuple[int, str] | None: ...

    def compare_and_set_audit_anchor(
        self,
        expected: tuple[int, str] | None,
        replacement: tuple[int, str],
    ) -> bool: ...


class InMemoryKeyProvider:
    def __init__(self, key: bytes | None = None) -> None:
        self._key = key or secrets.token_bytes(32)
        self._audit_anchor: tuple[int, str] | None = None

    def get_key(self) -> bytes:
        return self._key

    def get_audit_anchor(self) -> tuple[int, str] | None:
        return self._audit_anchor

    def compare_and_set_audit_anchor(
        self,
        expected: tuple[int, str] | None,
        replacement: tuple[int, str],
    ) -> bool:
        if self._audit_anchor != expected:
            return False
        self._audit_anchor = replacement
        return True


class MacOSKeychainProvider:
    """Fail-closed seam; the host application must provide a platform binding."""

    def get_key(self) -> bytes:
        raise ControlError(
            "key_unavailable",
            "/ledger/key",
            "macOS Keychain provider is unavailable",
        )

    def get_audit_anchor(self) -> tuple[int, str] | None:
        raise ControlError(
            "key_unavailable",
            "/ledger/audit-anchor",
            "macOS Keychain provider is unavailable",
        )

    def compare_and_set_audit_anchor(
        self,
        expected: tuple[int, str] | None,
        replacement: tuple[int, str],
    ) -> bool:
        raise ControlError(
            "key_unavailable",
            "/ledger/audit-anchor",
            "macOS Keychain provider is unavailable",
        )


class EphemeralCredential:
    """A redacted, expiring in-memory credential handle for adapter use only."""

    def __init__(self, token: str, expires_at: float) -> None:
        if (
            not isinstance(token, str)
            or not token
            or any(character.isspace() for character in token)
        ):
            raise ControlError(
                "credential_invalid", "/connection/credential", "credential is required"
            )
        if expires_at <= time.time():
            raise ControlError(
                "credential_expired", "/connection/credential", "credential has expired"
            )
        self._value = bytearray(token.encode("utf-8"))
        self.expires_at = expires_at
        self.closed = False

    def reveal(self) -> str:
        if self.closed or time.time() >= self.expires_at:
            raise ControlError(
                "credential_expired", "/connection/credential", "credential has expired"
            )
        return self._value.decode("utf-8")

    def close(self) -> None:
        for index in range(len(self._value)):
            self._value[index] = 0
        self.closed = True

    def __repr__(self) -> str:
        return "<EphemeralCredential redacted>"


@dataclass(frozen=True)
class Connection:
    id: str
    origin: str
    tenant_fingerprint: str
    actor: str
    permissions: tuple[str, ...]
    version: str
    pinned_addresses: tuple[str, ...]
    allow_private_origin: bool
