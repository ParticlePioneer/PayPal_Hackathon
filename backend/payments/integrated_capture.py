"""Merchant-only simulated fulfillment and full Sandbox capture."""
import hmac
import os
from uuid import uuid4

from fastapi import HTTPException

from . import provider
from .harness import database


def require_merchant(authorization):
    if os.getenv("B4_ENABLED", "").lower() != "true" or os.getenv("B5_CAPTURE_ENABLED", "").lower() != "true":
        raise HTTPException(404, "Not found")
    secret = os.getenv("B4_MERCHANT_TOKEN", "")
    if len(secret) < 32 or not authorization or not authorization.startswith("Bearer ") or not hmac.compare_digest(authorization[7:].encode(), secret.encode()):
        raise HTTPException(401, "Merchant authentication required")


def get_authorization(conn, authorization_id):
    # Joining the committed domain claim excludes standalone harness authorizations.
    row = conn.execute(
        "SELECT p.* FROM payment_operations p JOIN domain_authorization_claims c ON c.operation_id = p.operation_id AND c.quote_id = p.quote_id "
        "JOIN domain_quotes q ON q.id = p.quote_id AND q.session_id = p.session_id "
        "WHERE p.operation_type = 'authorize' AND p.status = 'succeeded' AND p.paypal_authorization_id = %s "
        "AND c.state = 'committed' AND q.state = 'allocated' AND q.total_cents = p.amount_cents AND q.currency = p.currency FOR UPDATE OF p",
        (authorization_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Integrated authorization not found")
    return row


def fulfill(authorization_id, authorization, simulated):
    require_merchant(authorization)
    if simulated is not True:
        raise HTTPException(422, "Explicit simulated fulfillment acknowledgement required")
    with database() as conn:
        auth = get_authorization(conn, authorization_id)
        conn.execute("INSERT INTO payment_fulfillments (authorization_operation_id) VALUES (%s) ON CONFLICT DO NOTHING", (auth["operation_id"],))
    return {"status": "fulfilled", "simulated": True}


def capture(authorization_id, authorization, fault):
    require_merchant(authorization)
    with database() as conn:
        auth = get_authorization(conn, authorization_id)
        if not conn.execute("SELECT 1 FROM payment_fulfillments WHERE authorization_operation_id = %s", (auth["operation_id"],)).fetchone():
            raise HTTPException(409, "Confirm simulated fulfillment before capture")
        operation = conn.execute("SELECT * FROM payment_operations WHERE quote_id = %s AND operation_type = 'capture'", (auth["quote_id"],)).fetchone()
        if not operation:
            operation_id = uuid4().hex
            operation = conn.execute(
                "INSERT INTO payment_operations (operation_id, quote_id, session_id, operation_type, status, amount_cents, currency, paypal_request_id, paypal_order_id, paypal_authorization_id) "
                "VALUES (%s, %s, %s, 'capture', 'pending', %s, %s, %s, %s, %s) RETURNING *",
                (operation_id, auth["quote_id"], auth["session_id"], auth["amount_cents"], auth["currency"], operation_id, auth["paypal_order_id"], authorization_id),
            ).fetchone()
        operation_id = operation["operation_id"]
    # Operation is committed before the provider call; this lock serializes retries.
    result = None
    with database() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("b5-capture:" + operation_id,))
        operation = conn.execute("SELECT *, created_at > clock_timestamp() - interval '1 hour' AS retry_allowed FROM payment_operations WHERE operation_id = %s FOR UPDATE", (operation_id,)).fetchone()
        if operation["status"] == "succeeded" and operation["paypal_capture_id"]:
            return {"status": "captured", "capture_id": operation["paypal_capture_id"]}
        if operation["status"] not in ("pending", "unknown") or not operation["retry_allowed"]:
            raise HTTPException(409, "Capture requires manual reconciliation")
        try:
            result = provider.capture_authorization(authorization_id, operation["amount_cents"], operation["paypal_request_id"])
            amount = result.get("amount", {})
            expected = f"{operation['amount_cents'] // 100}.{operation['amount_cents'] % 100:02d}"
            capture_id = result.get("id")
            if not isinstance(capture_id, str) or not capture_id or result.get("status") != "COMPLETED" or amount.get("currency_code") != operation["currency"] or amount.get("value") != expected:
                raise provider.ProviderError("Unverified capture")
            if os.getenv("B5_ALLOW_FAULT_INJECTION", "").lower() == "true" and fault == "true":
                raise provider.ProviderError("Simulated lost response")
        except (provider.ProviderError, AttributeError, TypeError):
            conn.execute("UPDATE payment_operations SET status = 'unknown', updated_at = clock_timestamp() WHERE operation_id = %s", (operation_id,))
            result = None
        else:
            conn.execute("UPDATE payment_operations SET status = 'succeeded', paypal_capture_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s", (capture_id, operation_id))
    if result is None:
        raise HTTPException(503, "Capture outcome unknown; retry the same authorization within one hour")
    return {"status": "captured", "capture_id": capture_id}
