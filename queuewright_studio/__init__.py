"""Compatibility package for the original Queuewright Studio imports.

New code should import from :mod:`queuewright.studio`.
"""

from queuewright.studio import StudioService, create_server

__all__ = ["StudioService", "create_server"]
