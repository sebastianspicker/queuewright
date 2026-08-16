"""Private identity-response verification for connection setup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models import ControlError, SAFE_KEY, _validate_addresses


@dataclass(frozen=True)
class _IdentityVerifier:
    canonical_origin: str
    host: str
    pinned: tuple[str, ...]
    allow_private_origin: bool

    def _validated_identity(self, identity: Any) -> tuple[tuple[str, str, str], list[str]]:
        self._require_identity_shape(identity)
        self._require_identity_binding(identity)
        permissions = self._identity_permissions(identity)
        return self._identity_claims(identity), permissions

    @staticmethod
    def _require_identity_shape(identity: Any) -> None:
        required = {
            "canonical_origin",
            "tenant_fingerprint",
            "actor",
            "permissions",
            "version",
            "resolved_addresses",
            "redirected",
        }
        if not isinstance(identity, Mapping) or set(identity) != required:
            raise ControlError(
                "identity_invalid", "/connection", "identity response shape is invalid"
            )

    def _require_identity_binding(self, identity: Mapping[str, Any]) -> None:
        if (
            identity["canonical_origin"] != self.canonical_origin
            or identity["redirected"] is not False
        ):
            raise ControlError(
                "identity_invalid",
                "/connection/origin",
                "redirected or off-origin identity response is forbidden",
            )
        identity_addresses = _validate_addresses(
            self.host, identity["resolved_addresses"], self.allow_private_origin
        )
        if identity_addresses != self.pinned:
            raise ControlError(
                "identity_invalid",
                "/connection/resolved_addresses",
                "identity transport did not use the pinned address set",
            )

    @staticmethod
    def _identity_permissions(identity: Mapping[str, Any]) -> list[str]:
        permissions = identity["permissions"]
        if not isinstance(permissions, list):
            raise ControlError(
                "identity_invalid",
                "/connection/permissions",
                "permissions are invalid",
            )
        if not all(
            isinstance(item, str) and SAFE_KEY.fullmatch(item) for item in permissions
        ):
            raise ControlError(
                "identity_invalid",
                "/connection/permissions",
                "permissions are invalid",
            )
        if "admin" in permissions:
            raise ControlError(
                "identity_invalid",
                "/connection/permissions",
                "permissions are invalid",
            )
        return permissions

    @staticmethod
    def _identity_claims(identity: Mapping[str, Any]) -> tuple[str, str, str]:
        claims = [identity[field] for field in ("tenant_fingerprint", "actor", "version")]
        if not all(isinstance(value, str) and value for value in claims):
            raise ControlError(
                "identity_invalid", "/connection", "identity claims are incomplete"
            )
        return (str(claims[0]), str(claims[1]), str(claims[2]))
