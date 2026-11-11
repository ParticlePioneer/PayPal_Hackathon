"""Minimal PayPal Sandbox Orders client. Never log credentials or responses."""
import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = "https://api-m.sandbox.paypal.com"

class ProviderError(Exception):
    """The provider outcome may be unknown."""


def request(path, data, headers):
    req = Request(BASE + path, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=20) as response:
            result = json.load(response)
            if not isinstance(result, dict):
                raise ProviderError("Unexpected PayPal response")
            return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise ProviderError("PayPal request failed or outcome is unknown") from None


def token():
    client = os.getenv("PAYPAL_CLIENT_ID", "")
    secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
    if not client or not secret:
        raise ProviderError("PayPal Sandbox credentials are not configured")
    credentials = base64.b64encode(f"{client}:{secret}".encode()).decode()
    result = request("/v1/oauth2/token", b"grant_type=client_credentials", {"Authorization": "Basic " + credentials, "Content-Type": "application/x-www-form-urlencoded"})
    access_token = result.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ProviderError("PayPal returned an invalid token response")
    return access_token


def call(path, payload, request_id):
    access_token = token()
    return request(path, json.dumps(payload).encode(), {"Authorization": "Bearer " + access_token, "Content-Type": "application/json", "PayPal-Request-Id": request_id, "Prefer": "return=representation"})


def create_order(cents, request_id):
    if type(cents) is not int or cents <= 0:
        raise ValueError("Invalid amount")
    amount = f"{cents // 100}.{cents % 100:02d}"
    return call("/v2/checkout/orders", {"intent": "AUTHORIZE", "purchase_units": [{"amount": {"currency_code": "USD", "value": amount}}]}, request_id)


def authorize_order(order_id, request_id):
    return call("/v2/checkout/orders/" + quote(order_id, safe="") + "/authorize", {}, request_id)
