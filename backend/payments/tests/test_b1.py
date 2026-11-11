import unittest
from unittest.mock import patch
from backend.payments.sandbox_auth import check_sandbox_auth
from backend.payments.test_quote_adapter import QuoteUnavailable, TestQuoteAdapter


class AdapterTests(unittest.TestCase):
    def test_claim_retry_release_and_ownership(self):
        adapter = TestQuoteAdapter()
        quote = adapter.claim_for_authorization("test-session", "test-usd-1", "op")
        self.assertEqual(quote.total_cents, 100)
        self.assertEqual(adapter.claim_for_authorization("test-session", "test-usd-1", "op"), quote)
        with self.assertRaises(QuoteUnavailable):
            adapter.claim_for_authorization("other", "test-usd-1", "op")
        with self.assertRaises(QuoteUnavailable):
            adapter.claim_for_authorization("test-session", "test-usd-1", "other-op")
        adapter.release_claim("op")
        adapter.release_claim("op")
        adapter.claim_for_authorization("test-session", "test-usd-1", "other-op")
        adapter.commit_allocation("other-op")
        adapter.commit_allocation("other-op")
        adapter.release_claim("other-op")
        with self.assertRaises(QuoteUnavailable):
            adapter.claim_for_authorization("test-session", "test-usd-1", "third-op")

    def test_expired_and_conflict(self):
        for scenario in ("expired", "conflict"):
            with self.subTest(scenario=scenario), self.assertRaises(QuoteUnavailable):
                TestQuoteAdapter(scenario).claim_for_authorization("test-session", "test-usd-1", "op")

    def test_empty_operation_cannot_commit(self):
        with self.assertRaises(QuoteUnavailable):
            TestQuoteAdapter().commit_allocation("")


class OAuthTests(unittest.TestCase):
    def test_missing_credentials_never_calls_network(self):
        with patch("backend.payments.sandbox_auth.urlopen") as call:
            with self.assertRaises(ValueError):
                check_sandbox_auth("", "")
            call.assert_not_called()

    def test_request_is_sandbox_and_token_is_not_returned(self):
        with patch("backend.payments.sandbox_auth.urlopen") as call:
            call.return_value.__enter__.return_value.read.return_value = b'{"access_token":"secret-token"}'
            self.assertIsNone(check_sandbox_auth("id", "secret"))
            self.assertEqual(call.call_args.args[0].full_url, "https://api-m.sandbox.paypal.com/v1/oauth2/token")


if __name__ == "__main__":
    unittest.main()
