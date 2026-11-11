import os
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from backend.main import app
from backend.payments import harness


class HarnessAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, base_url="https://testserver")

    def test_harness_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.client.get("/health").status_code, 200)
            self.assertEqual(self.client.get("/test-checkout").status_code, 404)
            self.assertEqual(self.client.post("/api/test-checkout/session").status_code, 404)

    def test_cross_origin_cannot_start_a_session(self):
        with patch.dict(os.environ, {"B2_HARNESS_ENABLED": "true"}, clear=True):
            response = self.client.post("/api/test-checkout/session", headers={"origin": "https://other.test"})
            self.assertEqual(response.status_code, 403)

    def test_missing_session_cannot_access_quote(self):
        with patch.dict(os.environ, {"B2_HARNESS_ENABLED": "true"}, clear=True):
            response = self.client.get("/api/payments/quotes/test_quote")
            self.assertEqual(response.status_code, 401)

    def test_empty_credentials_do_not_create_a_quote(self):
        with patch.dict(os.environ, {"B2_HARNESS_ENABLED": "true"}, clear=True), patch.object(harness, "database") as database:
            response = self.client.post("/api/test-checkout/session", headers={"origin": "https://testserver"})
            self.assertEqual(response.status_code, 503)
            database.assert_not_called()

    def test_authorization_is_persisted_and_repeat_does_not_call_paypal(self):
        cookie = "a" * 43
        headers = {"origin": "https://testserver"}
        order = {"quote_id": "test_quote"}
        responses = [{"quote_id": "test_quote"}, None, {"valid": True}, None, None,
                     order, {"status": "succeeded", "paypal_authorization_id": "AUTH-1"}]
        conn = MagicMock()
        conn.execute.side_effect = [MagicMock(fetchone=MagicMock(return_value=row)) for row in responses]

        @contextmanager
        def fake_database():
            yield conn

        provider_response = {"purchase_units": [{"payments": {"authorizations": [{
            "id": "AUTH-1", "status": "CREATED", "amount": {"currency_code": "USD", "value": "1.00"}
        }]}}]}
        with patch.dict(os.environ, {"B2_HARNESS_ENABLED": "true"}, clear=True), patch.object(harness, "database", fake_database), patch.object(harness.provider, "authorize_order", return_value=provider_response) as call:
            self.client.cookies.set("b2_session", cookie)
            first = self.client.post("/api/payments/orders/ORDER-1/authorize", headers=headers)
            second = self.client.post("/api/payments/orders/ORDER-1/authorize", headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["authorization_id"], "AUTH-1")
        self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
