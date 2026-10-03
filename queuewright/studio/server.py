"""Bounded loopback HTTP transport for the Studio API."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ..contracts.json import canonical_json
from .input import read_json_body
from .routes import StudioService, error_envelope

__all__ = ["MAX_BODY_BYTES", "create_server", "serve"]


HOST = "127.0.0.1"
PORT = 8765
MAX_BODY_BYTES = 2 * 1024 * 1024
JSON_CONTENT_TYPE = "application/json"


def _silence_log_message(*_args: Any) -> None:
    return


class _StudioHandler(BaseHTTPRequestHandler):
    server_version = "ZammadStudio/1.0"
    protocol_version = "HTTP/1.1"

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        rendered = canonical_json(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", JSON_CONTENT_TYPE)
        self.send_header("Content-Length", str(len(rendered)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(rendered)

    def _request_is_local(self) -> tuple[bool, dict[str, str] | None]:
        host = self.headers.get("Host")
        origin = self.headers.get("Origin")
        allowed_host = f"{HOST}:{self.server.server_port}"
        if host != allowed_host:
            return False, error_envelope(
                "invalid_host",
                "Host",
                "Host must target the loopback service",
            )
        allowed_origins = {f"http://{allowed_host}", "http://127.0.0.1:5173"}
        if origin is not None and origin not in allowed_origins:
            return False, error_envelope(
                "invalid_origin",
                "Origin",
                "Origin must be the loopback service",
            )
        return True, None

    def _body(self) -> tuple[Any | None, tuple[int, dict[str, Any]] | None]:
        return read_json_body(
            self.headers,
            self.rfile,
            JSON_CONTENT_TYPE,
            MAX_BODY_BYTES,
            error_envelope,
        )

    def _handle(self) -> None:
        allowed, failure = self._request_is_local()
        if not allowed:
            self._respond(
                400,
                failure or error_envelope("invalid_request", "request", "request is invalid"),
            )
            return
        if self.command not in {"GET", "POST"}:
            self._respond(
                405,
                error_envelope(
                    "method_not_allowed", self.path, "method is not allowed"
                ),
            )
            return
        body: Any = None
        if self.command == "POST":
            body, failure = self._body()
            if failure is not None:
                self._respond(*failure)
                return
        status, payload = self.server.studio_service.dispatch(
            self.command, self.path, body
        )
        self._respond(status, payload)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_OPTIONS = _handle

    log_message = _silence_log_message


class StudioHTTPServer(ThreadingHTTPServer):
    studio_service: StudioService


def create_server(host: str = HOST, port: int = PORT) -> StudioHTTPServer:
    if host != HOST:
        raise ValueError("Studio service only binds to 127.0.0.1")
    server = StudioHTTPServer((host, port), _StudioHandler)
    server.studio_service = StudioService()
    return server


def serve() -> None:
    with create_server() as server:
        server.serve_forever()
