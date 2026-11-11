"""Verify PayPal Sandbox OAuth without exposing credentials or tokens."""

import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SANDBOX_TOKEN_URL = "https://api-m.sandbox.paypal.com/v1/oauth2/token"


def check_sandbox_auth(client_id: str, client_secret: str) -> None:
    if not client_id or not client_secret:
        raise ValueError("Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET first.")
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    request = Request(
        SANDBOX_TOKEN_URL,
        data=b"grant_type=client_credentials",
        headers={"Authorization": f"Basic {credentials}", "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"PayPal Sandbox authentication failed (HTTP {exc.code}).") from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError("Could not reach PayPal Sandbox. Check network access and retry.") from None
    if not result.get("access_token"):
        raise RuntimeError("PayPal Sandbox response did not contain an access token.")


def main() -> int:
    try:
        check_sandbox_auth(os.getenv("PAYPAL_CLIENT_ID", ""), os.getenv("PAYPAL_CLIENT_SECRET", ""))
    except (ValueError, RuntimeError) as exc:
        print(exc)
        return 1
    print("PayPal Sandbox OAuth succeeded. No token was printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
