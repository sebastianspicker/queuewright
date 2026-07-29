"""Loopback-only request dispatching for Queuewright's local control surface."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .core import ControlError, READ_METHODS, _strict_json


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    headers: Mapping[str, str]
    body: Any = None


@dataclass(frozen=True)
class Response:
    status: int
    body: Mapping[str, Any]


class LocalDispatcher:
    def __init__(self, host: str, origin: str, bootstrap_secret: str, routes: Mapping[str, tuple[str, ...]], session_ttl_seconds: int = 900, max_sessions: int = 4) -> None:
        if not re.fullmatch(r"127\.0\.0\.1(?::[0-9]{1,5})?", host):
            raise ControlError("host_invalid", "/dispatcher", "dispatcher must use numeric loopback")
        if origin != f"http://{host}":
            raise ControlError("origin_invalid", "/dispatcher", "origin must match loopback host")
        if not isinstance(bootstrap_secret, str) or len(bootstrap_secret) < 32:
            raise ControlError("bootstrap_invalid", "/dispatcher", "launcher bootstrap secret must contain at least 32 characters")
        self.host, self.origin = host, origin
        self._bootstrap_hash = hashlib.sha256(bootstrap_secret.encode()).digest()
        self._bootstrap_available = True
        self._sessions: dict[str, tuple[str, float]] = {}
        self._routes = {path: tuple(sorted(set(methods))) for path, methods in routes.items()}
        self.session_ttl_seconds, self.max_sessions = session_ttl_seconds, max_sessions

    def dispatch(self, request: Request, handler: Callable[[Request, str], Mapping[str, Any]]) -> Response:
        error = self._origin_error(request)
        if error:
            return error
        self._expire_sessions()
        if request.path == "/bootstrap" and request.method == "POST":
            return self._bootstrap(request)
        session_id, error = self._authorized_session(request)
        if error:
            return error
        try:
            return Response(200, _strict_json(handler(request, session_id), "response"))
        except ControlError as error:
            return Response(400, error.public())

    def revoke_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _origin_error(self, request: Request) -> Response | None:
        if request.headers.get("Host") == self.host and request.headers.get("Origin") == self.origin:
            return None
        return Response(403, ControlError("origin_forbidden", request.path, "Host and Origin must match").public())

    def _bootstrap(self, request: Request) -> Response:
        supplied = request.headers.get("X-Bootstrap-Token", "")
        allowed = self._bootstrap_available and hmac.compare_digest(hashlib.sha256(supplied.encode()).digest(), self._bootstrap_hash) and len(self._sessions) < self.max_sessions
        if not allowed:
            return Response(401, ControlError("bootstrap_denied", request.path, "one-time launcher bootstrap is required").public())
        self._bootstrap_available = False
        session_id, csrf = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        self._sessions[session_id] = (csrf, time.time() + self.session_ttl_seconds)
        return Response(201, {"session_id": session_id, "csrf": csrf})

    def _authorized_session(self, request: Request) -> tuple[str, Response | None]:
        if request.method not in self._routes.get(request.path, ()):
            return "", Response(404, ControlError("route_not_found", request.path, "route is unavailable").public())
        session_id = request.headers.get("X-Session", "")
        session = self._sessions.get(session_id)
        if not session:
            return "", Response(401, ControlError("session_required", request.path, "bootstrap session required").public())
        if request.method not in READ_METHODS and request.headers.get("X-CSRF-Token") != session[0]:
            return "", Response(403, ControlError("csrf_invalid", request.path, "valid CSRF token required").public())
        return session_id, None

    def _expire_sessions(self) -> None:
        now = time.time()
        self._sessions = {session_id: session for session_id, session in self._sessions.items() if session[1] > now}
