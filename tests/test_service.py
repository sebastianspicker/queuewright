"""Characterization tests for the stable loopback StudioService facade."""

from __future__ import annotations

import unittest

from queuewright_studio.service import StudioService


class StudioServiceFacadeTests(unittest.TestCase):
    def test_dispatch_preserves_loopback_health_and_not_found_contracts(self) -> None:
        service = StudioService()

        self.assertEqual(
            service.dispatch("GET", "/api/v1/health"),
            (200, {"status": "ok", "service": "queuewright-studio", "offline_only": True}),
        )
        self.assertEqual(
            service.dispatch("PUT", "/api/v1/health"),
            (404, {"code": "not_found", "path": "/api/v1/health", "message": "resource not found"}),
        )
        self.assertEqual(
            service.dispatch("POST", "/api/v1/import-bundle", []),
            (
                400,
                {
                    "code": "invalid_request",
                    "path": "/api/v1/import-bundle",
                    "message": "JSON object required",
                },
            ),
        )
