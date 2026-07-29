"""Bounded JSON request-body parsing for the loopback Studio server."""

from __future__ import annotations

import json
from typing import Any, BinaryIO, Mapping


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
        return json.loads(raw.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, (
            400,
            error("invalid_json", "body", "request body must be valid UTF-8 JSON"),
        )


def _content_length(
    raw_length: str | None, max_body_bytes: int, error: Any
) -> tuple[int, tuple[int, dict[str, Any]] | None]:
    try:
        length = int(raw_length) if raw_length is not None else -1
    except ValueError:
        length = -1
    if length < 0:
        return 0, (
            411,
            error("length_required", "Content-Length", "Content-Length is required"),
        )
    if length > max_body_bytes:
        return 0, (
            413,
            error("body_too_large", "body", "request body exceeds 2097152 bytes"),
        )
    return length, None
