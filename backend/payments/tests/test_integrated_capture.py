import os
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from backend.main import create_app
from backend.payments import integrated_capture, provider


class IntegratedCaptureTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())
        self.env = {"B4_ENABLED": "true", "B5_CAPTURE_ENABLED": "true", "B4_MERCHANT_TOKEN": "a" * 40, "SESSION_SECRET": "s" * 40}
        self.headers = {"Authorization": "Bearer " + "a" * 40}
        self.base = "/api/merchant/payments/authorizations/AUTH-1"

    def test_disabled_and_unauthorized_never_open_database(self):
        with patch.dict(os.environ, self.env, clear=True), patch.object(integrated_capture, "database") as database:
            self.assertEqual(self.client.post(self.base + "/capture").status_code, 401)
            self.assertEqual(self.client.post(self.base + "/fulfillment", headers=self.headers, json={"simulated": False}).status_code, 422)
            database.assert_not_called()
        with patch.dict(os.environ, {**self.env, "B5_CAPTURE_ENABLED": "false"}, clear=True), patch.object(integrated_capture, "database") as database:
            self.assertEqual(self.client.post(self.base + "/capture", headers=self.headers).status_code, 404)
            database.assert_not_called()

    def test_fulfillment_required_before_provider_call(self):
        auth = {"operation_id": "auth-op", "quote_id": "q1"}
        conn = MagicMock()
        conn.execute.side_effect = [MagicMock(fetchone=MagicMock(return_value=auth)), MagicMock(fetchone=MagicMock(return_value=None))]
        @contextmanager
        def db():
            yield conn
        with patch.dict(os.environ, self.env, clear=True), patch.object(integrated_capture, "database", db), patch.object(provider, "capture_authorization") as call:
            response = self.client.post(self.base + "/capture", headers=self.headers)
        self.assertEqual(response.status_code, 409)
        call.assert_not_called()

    def test_lost_response_retry_reuses_operation_and_returns_capture(self):
        auth = {"operation_id": "auth-op", "quote_id": "q1"}
        op = {"operation_id": "capture-op", "status": "unknown", "retry_allowed": True, "amount_cents": 36000, "currency": "USD", "paypal_request_id": "request-id", "paypal_capture_id": None}
        conn = MagicMock()
        attempt = [MagicMock(fetchone=MagicMock(return_value=auth)), MagicMock(fetchone=MagicMock(return_value=(1,))), MagicMock(fetchone=MagicMock(return_value=op)), MagicMock(), MagicMock(fetchone=MagicMock(return_value=op)), MagicMock()]
        conn.execute.side_effect = attempt + attempt
        @contextmanager
        def db():
            yield conn
        completed = {"id": "capture-1", "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "360.00"}}
        with patch.dict(os.environ, {**self.env, "B5_ALLOW_FAULT_INJECTION": "true"}, clear=True), patch.object(integrated_capture, "database", db), patch.object(provider, "capture_authorization", return_value=completed) as call:
            first = self.client.post(self.base + "/capture", headers={**self.headers, "X-B5-Simulate-Lost-Response": "true"})
            second = self.client.post(self.base + "/capture", headers=self.headers)
        self.assertEqual(first.status_code, 503)
        self.assertEqual(second.json(), {"status": "captured", "capture_id": "capture-1"})
        self.assertEqual(call.call_args_list[0], call.call_args_list[1])
        self.assertEqual(call.call_args.args, ("AUTH-1", 36000, "request-id"))

    def test_wrong_capture_amount_stays_unknown(self):
        auth = {"operation_id": "auth-op", "quote_id": "q1"}
        op = {"operation_id": "capture-op", "status": "pending", "retry_allowed": True, "amount_cents": 36000, "currency": "USD", "paypal_request_id": "request-id"}
        conn = MagicMock()
        conn.execute.side_effect = [MagicMock(fetchone=MagicMock(return_value=auth)), MagicMock(fetchone=MagicMock(return_value=(1,))), MagicMock(fetchone=MagicMock(return_value=op)), MagicMock(), MagicMock(fetchone=MagicMock(return_value=op)), MagicMock()]
        @contextmanager
        def db():
            yield conn
        invalid = {"id": "capture-1", "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "1.00"}}
        with patch.dict(os.environ, self.env, clear=True), patch.object(integrated_capture, "database", db), patch.object(provider, "capture_authorization", return_value=invalid):
            response = self.client.post(self.base + "/capture", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertIn("status = 'unknown'", conn.execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
