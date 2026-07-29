"""ControlPlane composition root."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from .control_connection import ControlConnectionMixin
from .control_evidence import ControlEvidenceMixin
from .control_recovery import ControlRecoveryMixin
from .control_workflow import ControlWorkflowMixin
from .ledger import Ledger
from .models import AdapterPolicy, Connection, EphemeralCredential, Preview


class ControlPlane(
    ControlConnectionMixin,
    ControlWorkflowMixin,
    ControlRecoveryMixin,
    ControlEvidenceMixin,
):
    STATES = {
        "disconnected",
        "connected",
        "discovered",
        "previewed",
        "approved",
        "applying",
        "applied",
        "verified",
        "drift_detected",
        "outcome_ambiguous",
        "partially_applied",
        "rolling_back",
        "rolled_back",
        "manual_recovery",
    }

    def __init__(
        self,
        ledger: Ledger,
        policy: AdapterPolicy,
        transport: Callable[..., Any],
        resolver: Callable[[str], Sequence[str]] | None = None,
    ) -> None:
        self.ledger = ledger
        self.policy = policy
        self.transport = transport
        self.resolver = resolver
        self.connection: Connection | None = None
        self._credential: EphemeralCredential | None = None
        self.preview: Preview | None = None
        self._approved_hash: str | None = None
        self.session_state = "disconnected"
