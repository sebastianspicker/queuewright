"""Bounded JSON request-body parsing for the loopback Studio server."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, BinaryIO

from ..contracts.safety import SafeJsonError, validate_json_depth


def read_json_body(
    headers: Mapping[str, str],
    body_stream: BinaryIO,
    content_type: str,
    max_body_bytes: int,
    error: Any,
) -> tuple[Any | None, tuple[int, dict[str, Any]] | None]:
    if headers.get("Content-Type") != content_type:
        return None, (
            415,
            error(
                "unsupported_media_type",
                "Content-Type",
                "Content-Type must be application/json",
            ),
        )
    length, failure = _content_length(headers.get("Content-Length"), max_body_bytes, error)
    if failure is not None:
        return None, failure
    raw = body_stream.read(length)
    if len(raw) != length:
        return None, (400, error("invalid_request", "body", "request body is incomplete"))
    try:
        value = json.loads(raw.decode("utf-8"))
        validate_json_depth(value, "body")
        return value, None
    except SafeJsonError as failure:
        return None, (400, error("invalid_json", failure.path, failure.message))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None, (
            400,
            error("invalid_json", "body", "request body must be valid UTF-8 JSON"),
        )


def _content_length(
    raw_length: str | None, max_body_bytes: int, error: Any
) -> tuple[int, tuple[int, dict[str, Any]] | None]:
    if raw_length is None or not raw_length.isascii() or not raw_length.isdigit():
        return 0, (
            411,
            error("length_required", "Content-Length", "Content-Length is required"),
        )
    normalized_length = raw_length.lstrip("0") or "0"
    maximum = str(max_body_bytes)
    if (len(normalized_length), normalized_length) > (len(maximum), maximum):
        return 0, (
            413,
            error("body_too_large", "body", f"request body exceeds {max_body_bytes} bytes"),
        )
    length = int(normalized_length)
    return length, None
