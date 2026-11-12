import unittest
from unittest.mock import patch
from backend.integration import create_negotiation_router
from fastapi.testclient import TestClient
from backend.main import app


class IntegrationSetupTests(unittest.TestCase):
    def test_requires_explicit_seller_floor(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(RuntimeError, "MERCHANT_MINIMUM_TOTAL_CENTS"):
            create_negotiation_router()

    def test_builds_domain_router_without_contacting_providers(self):
        env = {"DATABASE_URL": "postgresql://user:pass@localhost/test", "GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "gemini-3.6-flash", "MERCHANT_MINIMUM_TOTAL_CENTS": "30000"}
        with patch.dict("os.environ", env, clear=True):
            router = create_negotiation_router()
        self.assertIn("/api/negotiations", {route.path for route in router.routes})

    def test_seed_requires_explicit_acknowledgement(self):
        with patch.dict("os.environ", {"B4_SEED_SCENARIO": "split"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "explicit acknowledgement"):
                with TestClient(app):
                    pass
