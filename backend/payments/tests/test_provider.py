import unittest
from unittest.mock import patch
from backend.payments import provider

class ProviderTests(unittest.TestCase):
    def test_create_order_uses_server_amount_and_authorize_intent(self):
        with patch.object(provider, "call", return_value={"id": "order"}) as call:
            self.assertEqual(provider.create_order(100, "operation"), {"id": "order"})
        path, body, request_id = call.call_args.args
        self.assertEqual(path, "/v2/checkout/orders")
        self.assertEqual(body["intent"], "AUTHORIZE")
        self.assertEqual(body["purchase_units"][0]["amount"], {"currency_code": "USD", "value": "1.00"})
        self.assertEqual(request_id, "operation")

    def test_authorize_path_escapes_order_id(self):
        with patch.object(provider, "call") as call:
            provider.authorize_order("abc/def", "operation")
        self.assertEqual(call.call_args.args[0], "/v2/checkout/orders/abc%2Fdef/authorize")

    def test_invalid_amount_rejected(self):
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                provider.create_order(value, "operation")

    def test_missing_credentials_do_not_contact_provider(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(provider, "request") as request:
            with self.assertRaises(provider.ProviderError):
                provider.token()
            request.assert_not_called()

if __name__ == "__main__":
    unittest.main()
