import unittest
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from backend.domain.database import DomainError
from backend.payments import integrated, provider
from backend.payments.domain_handoff import PaymentUncertain, authorize_reserved_quote


class IntegratedPaymentTests(unittest.TestCase):
    def setUp(self):
        self.lock_patch = patch.object(integrated, "payment_lock", lambda _: nullcontext())
        self.lock_patch.start()
        self.addCleanup(self.lock_patch.stop)
        self.order_patch = patch.object(integrated, "order_quote", return_value="q1")
        self.order_patch.start()
        self.addCleanup(self.order_patch.stop)
        self.request = SimpleNamespace(state=SimpleNamespace(session_id="s_buyer"), headers={"origin": "https://example.test", "host": "example.test"})
        self.quote = SimpleNamespace(id="q1", state="reserved", total_cents=35400, currency="USD")
        self.quotes = MagicMock()
        self.quotes.get_quote.return_value = self.quote
        self.connection = MagicMock()

    def database(self):
        @contextmanager
        def connection():
            yield self.connection
        return connection()

    def test_order_uses_quote_amount_and_persists_before_provider(self):
        self.connection.execute.side_effect = [MagicMock(), MagicMock(fetchone=MagicMock(return_value=None)), MagicMock(), MagicMock()]
        with patch.object(integrated, "database", self.database), patch.object(integrated, "adapter", return_value=self.quotes), patch.object(provider, "create_order", return_value={"id": "order"}) as call:
            self.assertEqual(integrated.create_order("q1", self.request), {"id": "order"})
        self.assertEqual(call.call_args.args[0], 35400)
        inserted = self.connection.execute.call_args_list[2]
        self.assertIn("INSERT INTO payment_operations", inserted.args[0])
        self.assertEqual(inserted.args[1][3], 35400)

    def test_foreign_quote_never_calls_provider(self):
        self.quotes.get_quote.side_effect = DomainError("not_found")
        with patch.object(integrated, "database", self.database), patch.object(integrated, "adapter", return_value=self.quotes), patch.object(provider, "create_order") as call:
            with self.assertRaises(HTTPException) as error:
                integrated.create_order("q1", self.request)
        self.assertEqual(error.exception.status_code, 404)
        call.assert_not_called()

    def test_amount_mismatch_does_not_call_provider(self):
        self.quotes.claim_for_authorization.return_value = self.quote
        with patch.object(provider, "authorize_order") as call, self.assertRaises(PaymentUncertain):
            authorize_reserved_quote(self.quotes, "s_buyer", "q1", "operation", "order", expected_cents=100)
        call.assert_not_called()
        self.quotes.release_claim.assert_not_called()

    def test_auth_claim_storage_error_stays_unknown(self):
        order = {"quote_id": "q1", "amount_cents": 35400, "currency": "USD"}
        self.connection.execute.side_effect = [MagicMock(fetchone=MagicMock(return_value=order)), MagicMock(fetchone=MagicMock(return_value=None)), MagicMock(), MagicMock()]
        with patch.object(integrated, "database", self.database), patch.object(integrated, "adapter", return_value=self.quotes), patch.object(integrated, "authorize_reserved_quote", side_effect=DomainError("storage_unavailable")):
            with self.assertRaises(HTTPException) as error:
                integrated.authorize("order", self.request)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.connection.execute.call_args.args[1][0], "unknown")

    def test_reconciliation_requires_merchant_secret(self):
        with patch.dict("os.environ", {"B4_MERCHANT_TOKEN": "x" * 40}, clear=True), patch.object(integrated, "database") as database:
            with self.assertRaises(HTTPException) as error:
                integrated.reconcile("q1", "authorize", "Bearer incorrect")
        self.assertEqual(error.exception.status_code, 401)
        database.assert_not_called()

    def test_reconciliation_reuses_original_claim_and_request_id(self):
        row = {"operation_id": "old-operation", "status": "unknown", "retry_allowed": True, "recovery_ready": True, "session_id": "s_buyer", "paypal_order_id": "order", "amount_cents": 35400}
        self.connection.execute.side_effect = [MagicMock(), MagicMock(fetchone=MagicMock(return_value=row)), MagicMock()]
        result = SimpleNamespace(authorization_id="auth1", amount_cents=35400)
        with patch.dict("os.environ", {"B4_MERCHANT_TOKEN": "x" * 40}, clear=True), patch.object(integrated, "database", self.database), patch.object(integrated, "adapter", return_value=self.quotes), patch.object(integrated, "authorize_reserved_quote", return_value=result) as call:
            response = integrated.reconcile("q1", "authorize", "Bearer " + "x" * 40)
        self.assertEqual(response["authorization_id"], "auth1")
        self.assertEqual(call.call_args.args, (self.quotes, "s_buyer", "q1", "old-operation", "order"))
        self.assertEqual(call.call_args.kwargs["expected_cents"], 35400)
        self.assertTrue(callable(call.call_args.kwargs["on_verified"]))

    def test_reconciliation_with_saved_authorization_finishes_allocation_without_replay(self):
        row = {"operation_id": "old-operation", "status": "unknown", "retry_allowed": True, "recovery_ready": True, "session_id": "s_buyer", "paypal_order_id": "order", "paypal_authorization_id": "auth-saved", "amount_cents": 35400}
        self.connection.execute.side_effect = [MagicMock(), MagicMock(fetchone=MagicMock(return_value=row)), MagicMock()]
        with patch.dict("os.environ", {"B4_MERCHANT_TOKEN": "x" * 40}, clear=True), patch.object(integrated, "database", self.database), patch.object(integrated, "adapter", return_value=self.quotes), patch.object(provider, "authorize_order") as call:
            result = integrated.reconcile("q1", "authorize", "Bearer " + "x" * 40)
        self.assertEqual(result["authorization_id"], "auth-saved")
        self.quotes.claim_for_authorization.assert_called_once_with("s_buyer", "q1", "old-operation")
        self.quotes.commit_allocation.assert_called_once_with("old-operation")
        call.assert_not_called()

    def test_reconciliation_rejects_old_uncertain_operation(self):
        row = {"status": "unknown", "retry_allowed": False, "recovery_ready": True}
        self.connection.execute.side_effect = [MagicMock(), MagicMock(fetchone=MagicMock(return_value=row))]
        with patch.dict("os.environ", {"B4_MERCHANT_TOKEN": "x" * 40}, clear=True), patch.object(integrated, "database", self.database), patch.object(provider, "create_order") as call:
            with self.assertRaises(HTTPException) as error:
                integrated.reconcile("q1", "order", "Bearer " + "x" * 40)
        self.assertEqual(error.exception.status_code, 409)
        call.assert_not_called()
