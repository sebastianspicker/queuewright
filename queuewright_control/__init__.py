"""Local, transport-injected control-plane primitives for Zammad changes.

This package deliberately contains no HTTP client and never imports
``queuewright``.  A host application supplies the resource transport.
"""

from .core import (
    AdapterPolicy,
    Capability,
    CapabilityDiscovery,
    Connection,
    ControlError,
    ControlPlane,
    InMemoryKeyProvider,
    Ledger,
    LocalDispatcher,
    MacOSKeychainProvider,
    MasterKeyProvider,
    Operation,
    Preview,
    Request,
    Response,
)

__all__ = [
    "AdapterPolicy", "Capability", "CapabilityDiscovery", "Connection",
    "ControlError", "ControlPlane", "InMemoryKeyProvider", "Ledger", "MasterKeyProvider",
    "LocalDispatcher", "MacOSKeychainProvider", "Operation", "Preview",
    "Request", "Response",
]
