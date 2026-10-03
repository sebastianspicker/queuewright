"""The single error type raised by project validation, migration, and compilation."""

from __future__ import annotations

from typing import Literal

from ..errors import ConfigurationError

ProjectErrorKind = Literal["malformed", "unprocessable"]


class ProjectError(ConfigurationError):
    """A project, bundle, or draft violates the portable project contract.

    ``path`` locates the fault; it is ``"project"`` when the fault concerns the
    project as a whole. ``kind`` classifies the fault per raise site:
    ``"malformed"`` means structurally wrong input (wrong type, missing or
    unsupported field), and ``"unprocessable"`` means well-formed input that
    violates a project rule. Callers choose how to report each kind.
    ``str(error)`` is the flattened
    text that canonical V2 callers have always reported: the bare message for
    whole-project faults, otherwise ``"<path>: <message>"``.
    """

    def __init__(
        self,
        message: str,
        *,
        path: str | None = None,
        kind: ProjectErrorKind = "unprocessable",
    ) -> None:
        super().__init__(message if path is None else f"{path}: {message}")
        self.path = "project" if path is None else path
        self.message = message
        self.kind: ProjectErrorKind = kind
