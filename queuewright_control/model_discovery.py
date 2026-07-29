"""Capability discovery models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .model_protocol import ControlError, _freeze, _hash, _strict_json

@dataclass(frozen=True)
class Capability:
    support: str
    delivery: str
    complete: bool
    items: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.support not in {
            "supported",
            "permission_blocked",
            "plan_unsupported",
            "version_unsupported",
            "unknown",
        }:
            raise ValueError("invalid support status")
        if self.delivery not in {
            "automated",
            "guided_manual",
            "verify_only",
            "unsupported",
        }:
            raise ValueError("invalid delivery status")
        object.__setattr__(
            self,
            "items",
            tuple(_freeze(dict(item)) for item in self.items),
        )


class CapabilityDiscovery:
    """Bounded pagination where ambiguity never becomes absence."""

    @staticmethod
    def pages(
        fetch: Callable[[int], tuple[int, Sequence[Mapping[str, Any]]]],
        *,
        max_pages: int = 100,
        page_size: int = 100,
    ) -> Capability:
        seen: set[str] = set()
        items: list[Mapping[str, Any]] = []
        for page in range(1, max_pages + 1):
            status, batch = fetch(page)
            try:
                normalized = tuple(
                    _strict_json(dict(item), f"page[{page}]") for item in batch
                )
            except (TypeError, ValueError, ControlError):
                return Capability("unknown", "unsupported", False, tuple(items))
            result = _page_result(status, normalized, seen, tuple(items), page_size)
            if result is not None:
                return result
            items.extend(normalized)
        return Capability("supported", "verify_only", False, tuple(items))


def _page_result(
    status: int,
    normalized: tuple[Any, ...],
    seen: set[str],
    items: tuple[Mapping[str, Any], ...],
    page_size: int,
) -> Capability | None:
    if status == 403:
        return Capability("permission_blocked", "unsupported", False, items)
    if status == 404 or not 200 <= status < 300:
        return Capability("unknown", "unsupported", False, items)
    signature = _hash(normalized)
    if signature in seen:
        return Capability("supported", "verify_only", False, items)
    seen.add(signature)
    if not normalized or len(normalized) < page_size:
        return Capability("supported", "automated", True, items + normalized)
    return None
