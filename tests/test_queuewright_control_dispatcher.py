"""Loopback dispatcher contract tests kept separate from control-plane recovery tests."""

from __future__ import annotations

import unittest

from queuewright_control import ControlError, LocalDispatcher, Request
from tests.control_test_support import BOOTSTRAP


class DispatcherTests(unittest.TestCase):
    def request(self, method: str, path: str, **headers: str) -> Request:
        return Request(
            method,
            path,
            {"Host": "127.0.0.1:9443", "Origin": "http://127.0.0.1:9443", **headers},
        )

    def test_one_time_bootstrap_route_and_csrf(self) -> None:
        dispatcher = LocalDispatcher(
            "127.0.0.1:9443",
            "http://127.0.0.1:9443",
            BOOTSTRAP,
            {"/preview": ("GET", "POST")},
        )
        denied = dispatcher.dispatch(self.request("POST", "/bootstrap"), lambda *_: {})
        self.assertEqual(denied.status, 401)
        boot = dispatcher.dispatch(
            self.request("POST", "/bootstrap", **{"X-Bootstrap-Token": BOOTSTRAP}),
            lambda *_: {},
        )
        self.assertEqual(boot.status, 201)
        replay = dispatcher.dispatch(
            self.request("POST", "/bootstrap", **{"X-Bootstrap-Token": BOOTSTRAP}),
            lambda *_: {},
        )
        self.assertEqual(replay.status, 401)
        session = str(boot.body["session_id"])
        no_csrf = dispatcher.dispatch(
            self.request("POST", "/preview", **{"X-Session": session}), lambda *_: {}
        )
        self.assertEqual(no_csrf.status, 403)
        ok = dispatcher.dispatch(
            self.request(
                "POST",
                "/preview",
                **{"X-Session": session, "X-CSRF-Token": str(boot.body["csrf"])},
            ),
            lambda *_: {"ok": True},
        )
        self.assertEqual(ok.body, {"ok": True})
        missing = dispatcher.dispatch(
            self.request("GET", "/arbitrary", **{"X-Session": session}), lambda *_: {}
        )
        self.assertEqual(missing.status, 404)

    def test_dispatcher_rejects_non_loopback_construction(self) -> None:
        with self.assertRaises(ControlError):
            LocalDispatcher("localhost:9443", "http://localhost:9443", BOOTSTRAP, {})
