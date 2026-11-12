import unittest
from unittest.mock import patch
from backend.integration import create_negotiation_router
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.domain.openrouter_client import OpenRouterActionClient
from backend.domain.model_config import ModelConfigurationError
from backend.domain.fixtures import buyer_fixture


class IntegrationSetupTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "DATABASE_URL": "postgresql://user:pass@localhost/test",
            "OPENROUTER_API_KEY": "private-openrouter-key",
            "OPENROUTER_MODEL": "example/explicit-model:free",
            "OPENROUTER_TIMEOUT_MS": "45000",
            "OPENROUTER_MAX_OUTPUT_TOKENS": "2048",
            "MERCHANT_MINIMUM_TOTAL_CENTS": "30000",
            "SESSION_SECRET": "s" * 40,
            "B4_ENABLED": "true",
        }

    def test_requires_explicit_seller_floor(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(RuntimeError, "MERCHANT_MINIMUM_TOTAL_CENTS"):
            create_negotiation_router()

    def test_builds_domain_router_without_contacting_providers(self):
        with patch.dict("os.environ", self.env, clear=True), patch("httpx.Client.send", side_effect=AssertionError("Unexpected network call")), patch("backend.domain.api.create_router") as router, self.assertLogs("uvicorn.error", level="INFO") as logs:
            create_negotiation_router()
        service = router.call_args.args[0]
        self.assertIsInstance(service.agent_source, OpenRouterActionClient)
        self.assertEqual(service.agent_source.settings.model, self.env["OPENROUTER_MODEL"])
        self.assertEqual(service.agent_source.settings.max_output_tokens, 2048)
        self.assertEqual(service.timeout_ms, 45000)
        seller = service.seller_factory(buyer_fixture().requirements)
        self.assertEqual(seller.policy.minimum_total_cents, 30000)
        self.assertEqual(seller.stock_batches, ())
        self.assertEqual(seller.offer_options, ())
        output = " ".join(logs.output)
        self.assertIn("provider=openrouter", output)
        self.assertIn("no provider request performed", output)
        for key in ("OPENROUTER_API_KEY", "DATABASE_URL", "SESSION_SECRET"):
            self.assertNotIn(self.env[key], output)

    def test_host_mounts_openrouter_routes_once_and_legacy_harness_is_off(self):
        with patch.dict("os.environ", self.env, clear=True), patch("backend.domain.openrouter_client.OpenRouterActionClient._generate") as generate, patch("backend.integration.create_negotiation_router", wraps=create_negotiation_router) as build:
            application = create_app()
            for _ in range(2):
                with TestClient(application) as client:
                    self.assertEqual(client.get("/health").json(), {"status": "ok"})
                    self.assertEqual(client.get("/test-checkout").status_code, 404)
                    self.assertEqual(client.post("/api/negotiations", json={}).status_code, 422)
            build.assert_called_once_with()
            generate.assert_not_called()

    def test_gemini_credentials_cannot_replace_missing_openrouter_key(self):
        env = {**self.env, "OPENROUTER_API_KEY": "", "GEMINI_API_KEY": "old-gemini-key"}
        with patch.dict("os.environ", env, clear=True), self.assertRaisesRegex(ModelConfigurationError, "OPENROUTER_API_KEY"):
            with TestClient(create_app()):
                pass

    def test_paid_model_fails_startup(self):
        with patch.dict("os.environ", {**self.env, "OPENROUTER_MODEL": "example/paid-model"}, clear=True), self.assertRaises(ModelConfigurationError):
            with TestClient(create_app()):
                pass

    def test_seed_requires_explicit_acknowledgement(self):
        with patch.dict("os.environ", {"B4_SEED_SCENARIO": "split"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "explicit acknowledgement"):
                with TestClient(create_app()):
                    pass
