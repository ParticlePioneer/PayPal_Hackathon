import os
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from backend.main import app
from backend.payments import capture, provider


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.environment = {"B2_HARNESS_ENABLED": "true", "B3_CAPTURE_ENABLED": "true", "B3_MERCHANT_TOKEN": "a" * 40}
        self.path = "/api/merchant/payments/authorizations/AUTH-1/capture"

    def test_capture_requires_merchant_authentication(self):
        with patch.dict(os.environ, self.environment, clear=True), patch.object(capture, "database") as database:
            self.assertEqual(self.client.post(self.path).status_code, 401)
            self.assertEqual(self.client.post(self.path, headers={"Authorization": "Bearer wrong"}).status_code, 401)
            database.assert_not_called()

    def test_capture_uses_stored_id_and_returns_completed_capture(self):
        auth = {"quote_id": "q", "session_id": "s", "amount_cents": 100, "currency": "USD", "paypal_order_id": "o"}
        operation = {"operation_id": "op", "status": "unknown", "retry_allowed": True, "amount_cents": 100, "paypal_request_id": "stable-id"}
        conn = MagicMock()
        conn.execute.side_effect = [MagicMock(fetchone=MagicMock(return_value=auth)), MagicMock(fetchone=MagicMock(return_value=operation)), MagicMock(), MagicMock(fetchone=MagicMock(return_value=operation)), MagicMock()]
        @contextmanager
        def database():
            yield conn
        response_data = {"id": "CAP-1", "status": "COMPLETED", "amount": {"value": "1.00", "currency_code": "USD"}}
        with patch.dict(os.environ, self.environment, clear=True), patch.object(capture, "database", database), patch.object(provider, "capture_authorization", return_value=response_data) as call:
            response = self.client.post(self.path, headers={"Authorization": "Bearer " + "a" * 40})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "captured", "capture_id": "CAP-1"})
        call.assert_called_once_with("AUTH-1", 100, "stable-id")

    def test_provider_capture_request_uses_authorization_not_order_id(self):
        with patch.object(provider, "call") as call:
            provider.capture_authorization("AUTH-1", 100, "request-id")
        self.assertEqual(call.call_args.args[0], "/v2/payments/authorizations/AUTH-1/capture")
        self.assertEqual(call.call_args.args[1]["amount"]["value"], "1.00")
        self.assertEqual(call.call_args.args[2], "request-id")

    def test_lost_response_retry_reuses_request_id(self):
        auth = {"quote_id": "q", "session_id": "s", "amount_cents": 100, "currency": "USD", "paypal_order_id": "o"}
        operation = {"operation_id": "op", "status": "unknown", "retry_allowed": True, "amount_cents": 100, "paypal_request_id": "stable-id"}
        one_attempt = [MagicMock(fetchone=MagicMock(return_value=auth)), MagicMock(fetchone=MagicMock(return_value=operation)), MagicMock(), MagicMock(fetchone=MagicMock(return_value=operation)), MagicMock()]
        conn = MagicMock()
        conn.execute.side_effect = one_attempt + one_attempt
        @contextmanager
        def database():
            yield conn
        completed = {"id": "CAP-1", "status": "COMPLETED", "amount": {"value": "1.00", "currency_code": "USD"}}
        with patch.dict(os.environ, self.environment, clear=True), patch.object(capture, "database", database), patch.object(provider, "capture_authorization", side_effect=[provider.ProviderError("lost response"), completed]) as call:
            headers = {"Authorization": "Bearer " + "a" * 40}
            first = self.client.post(self.path, headers=headers)
            second = self.client.post(self.path, headers=headers)
        self.assertEqual(first.status_code, 503)
        self.assertEqual(second.json()["capture_id"], "CAP-1")
        self.assertEqual(call.call_args_list[0], call.call_args_list[1])

    def test_fault_injection_discards_success_only_when_enabled(self):
        auth = {"quote_id": "q", "session_id": "s", "amount_cents": 100, "currency": "USD", "paypal_order_id": "o"}
        operation = {"operation_id": "op", "status": "pending", "retry_allowed": True, "amount_cents": 100, "paypal_request_id": "stable-id"}
        conn = MagicMock()
        conn.execute.side_effect = [MagicMock(fetchone=MagicMock(return_value=auth)), MagicMock(fetchone=MagicMock(return_value=operation)), MagicMock(), MagicMock(fetchone=MagicMock(return_value=operation)), MagicMock()]
        @contextmanager
        def database():
            yield conn
        completed = {"id": "CAP-1", "status": "COMPLETED", "amount": {"value": "1.00", "currency_code": "USD"}}
        environment = dict(self.environment, B3_ALLOW_FAULT_INJECTION="true")
        with patch.dict(os.environ, environment, clear=True), patch.object(capture, "database", database), patch.object(provider, "capture_authorization", return_value=completed):
            response = self.client.post(self.path, headers={"Authorization": "Bearer " + "a" * 40, "X-B3-Simulate-Lost-Response": "true"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("status = 'unknown'", conn.execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
