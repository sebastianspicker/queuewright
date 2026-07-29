"""Connection, discovery, and preview lifecycle mixin."""

from __future__ import annotations

import ipaddress
import secrets
import time
from typing import Any, Callable, Mapping, Sequence

from .models import (
    Capability, CapabilityDiscovery, Connection, ControlError, EphemeralCredential,
    Preview, SAFE_KEY, _canonical_origin, _validate_addresses,
)

class ControlConnectionMixin:
    def connect(
        self,
        origin: str,
        token: str,
        *,
        credential_ttl_seconds: int = 900,
        allow_private_origin: bool = False,
    ) -> Connection:
        canonical_origin, host = _canonical_origin(origin)
        pinned = self._resolved_addresses(host, allow_private_origin)
        credential = EphemeralCredential(token, time.time() + credential_ttl_seconds)
        try:
            identity = self.transport("identity", origin=canonical_origin, pinned_addresses=pinned, redirects=False, credential=credential)
            claims, permissions = self._validated_identity(identity, canonical_origin, host, pinned, allow_private_origin)
        except Exception:
            credential.close()
            raise
        self.disconnect()
        self._credential = credential
        self.connection = Connection(secrets.token_urlsafe(24), canonical_origin, claims[0], claims[1], tuple(sorted(set(permissions))), claims[2], pinned, allow_private_origin)
        self.preview = None
        self._approved_hash = None
        self.session_state = "connected"
        return self.connection

    def _resolved_addresses(self, host: str, allow_private_origin: bool) -> tuple[str, ...]:
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            resolved = [literal.compressed]
        elif self.resolver is not None:
            try:
                resolved = list(self.resolver(host))
            except Exception as error:
                raise ControlError(
                    "resolution_failed",
                    "/connection/origin",
                    "origin could not be resolved by the DNS-only resolver",
                ) from error
        else:
            raise ControlError(
                "resolution_required",
                "/connection/origin",
                "a DNS-only resolver is required before identity transport",
            )
        return _validate_addresses(host, resolved, allow_private_origin)

    @staticmethod
    def _validated_identity(identity: Any, canonical_origin: str, host: str, pinned: tuple[str, ...], allow_private_origin: bool) -> tuple[tuple[str, str, str], list[str]]:
        ControlConnectionMixin._require_identity_shape(identity)
        ControlConnectionMixin._require_identity_binding(identity, canonical_origin, host, pinned, allow_private_origin)
        permissions = ControlConnectionMixin._identity_permissions(identity)
        return ControlConnectionMixin._identity_claims(identity), permissions

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

    @staticmethod
    def _require_identity_binding(identity: Mapping[str, Any], canonical_origin: str, host: str, pinned: tuple[str, ...], allow_private_origin: bool) -> None:
        if (
            identity["canonical_origin"] != canonical_origin
                or identity["redirected"] is not False
        ):
            raise ControlError(
                    "identity_invalid",
                    "/connection/origin",
                    "redirected or off-origin identity response is forbidden",
            )
        identity_addresses = _validate_addresses(
            host, identity["resolved_addresses"], allow_private_origin
        )
        if identity_addresses != pinned:
            raise ControlError(
                    "identity_invalid",
                    "/connection/resolved_addresses",
                    "identity transport did not use the pinned address set",
            )

    @staticmethod
    def _identity_permissions(identity: Mapping[str, Any]) -> list[str]:
        permissions = identity["permissions"]
        if (
            not isinstance(permissions, list)
                or not all(
                    isinstance(item, str) and SAFE_KEY.fullmatch(item)
                    for item in permissions
                )
                or "admin" in permissions
        ):
            raise ControlError(
                    "identity_invalid",
                    "/connection/permissions",
                    "permissions are invalid",
            )
        return permissions


    @staticmethod
    def _identity_claims(identity: Mapping[str, Any]) -> tuple[str, str, str]:
        claims = [
                identity[field]
                for field in ("tenant_fingerprint", "actor", "version")
        ]
        if not all(isinstance(value, str) and value for value in claims):
            raise ControlError(
                    "identity_invalid", "/connection", "identity claims are incomplete"
            )
        return (str(claims[0]), str(claims[1]), str(claims[2]))

    def disconnect(self) -> None:
        if self._credential:
            self._credential.close()
        self._credential = None
        self.connection = None
        self.preview = None
        self._approved_hash = None
        self.session_state = "disconnected"

    def discover(
        self,
        fetch: Callable[[int], tuple[int, Sequence[Mapping[str, Any]]]],
    ) -> Capability:
        self._require_connection()
        capability = CapabilityDiscovery.pages(fetch)
        self.preview = None
        self._approved_hash = None
        self.session_state = "discovered"
        return capability

    def recoverable_runs(self) -> list[dict[str, Any]]:
        connection, _ = self._require_connection()
        return [
            run
            for run in self.ledger.incomplete_runs()
            if run["tenant_fingerprint"] == connection.tenant_fingerprint
        ]

    def resume_run(self, run_id: str) -> Preview:
        """Restore a protected preview for an incomplete durable run."""
        connection, _ = self._require_connection()
        run = self.ledger.run(run_id)
        self._require_recoverable_run(run, run_id)
        preview = self.ledger.load_preview(str(run["preview_hash"]))
        self._require_resumable_preview(preview, run, connection, run_id)
        for operation in preview.operations:
            self.policy.validate(operation, connection.permissions)
        self.preview = preview
        self._approved_hash = None
        self.session_state = str(run["state"])
        return preview

    @staticmethod
    def _require_recoverable_run(run: Mapping[str, Any] | None, run_id: str) -> None:
        if not run or run["state"] in {"verified", "rolled_back"}:
            raise ControlError("run_invalid", "/runs", "run is not recoverable", run_id)

    def _require_resumable_preview(self, preview: Preview, run: Mapping[str, Any], connection: Connection, run_id: str) -> None:
        if (
            preview.tenant_fingerprint != connection.tenant_fingerprint
            or preview.actor != connection.actor
            or preview.permissions != connection.permissions
            or preview.policy_hash != self.policy.digest
            or preview.project_id != run["project_id"]
        ):
            raise ControlError(
                "run_invalid",
                "/runs",
                "stored run does not match the current tenant, actor, permissions, or policy",
                run_id,
            )
