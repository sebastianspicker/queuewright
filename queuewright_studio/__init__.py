"""Local-only Studio service for inert Zammad configuration projects."""

from .service import StudioService, create_server

__all__ = ["StudioService", "create_server"]
