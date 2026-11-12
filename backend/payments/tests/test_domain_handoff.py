import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.domain.database import DomainError
from backend.payments import provider
from backend.payments.domain_handoff import PaymentUncertain, authorize_reserved_quote


class DomainHandoffTests(unittest.TestCase):
    def setUp(self):
        self.quotes = MagicMock()
        self.quotes.claim_for_authorization.return_value = SimpleNamespace(total_cents=35400, currency="USD")
        self.response = {"purchase_units": [{"payments": {"authorizations": [{"id": "auth", "status": "CREATED", "amount": {"currency_code": "USD", "value": "354.00"}}]}}]}

    def test_claim_and_matching_authorization_commit(self):
        with patch.object(provider, "authorize_order", return_value=self.response) as call:
            result = authorize_reserved_quote(self.quotes, "session", "quote", "operation", "order")
        self.quotes.claim_for_authorization.assert_called_once_with("session", "quote", "operation")
        call.assert_called_once_with("order", "operation")
        self.quotes.commit_allocation.assert_called_once_with("operation")
        self.assertEqual(result.amount_cents, 35400)

    def test_unknown_and_mismatched_amount_keep_claim(self):
        self.response["purchase_units"][0]["payments"]["authorizations"][0]["amount"]["value"] = "1.00"
        for result in (provider.ProviderError("timeout"), self.response):
            with self.subTest(result=type(result)), patch.object(provider, "authorize_order", side_effect=result if isinstance(result, Exception) else None, return_value=result):
                with self.assertRaises(PaymentUncertain):
                    authorize_reserved_quote(self.quotes, "session", "quote", "operation", "order")
        self.quotes.release_claim.assert_not_called()
        self.quotes.commit_allocation.assert_not_called()

    def test_allocation_failure_does_not_release_authorized_claim(self):
        self.quotes.commit_allocation.side_effect = DomainError("storage_unavailable")
        with patch.object(provider, "authorize_order", return_value=self.response), self.assertRaises(PaymentUncertain):
            authorize_reserved_quote(self.quotes, "session", "quote", "operation", "order")
        self.quotes.release_claim.assert_not_called()

    def test_verified_id_is_saved_before_allocation(self):
        events = []
        self.quotes.commit_allocation.side_effect = lambda _: events.append("allocation")
        with patch.object(provider, "authorize_order", return_value=self.response):
            authorize_reserved_quote(self.quotes, "session", "quote", "operation", "order", on_verified=lambda value: events.append(value))
        self.assertEqual(events, ["auth", "allocation"])
