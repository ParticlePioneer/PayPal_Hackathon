"""Merchant-only, Sandbox-only capture for the isolated B2 test harness.

This is not yet connected to Member A's fulfillment or quote lifecycle.
"""
import hmac
import os
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, StrictBool

from . import provider
from .harness import database, require_harness

router = APIRouter()


class FulfillmentRequest(BaseModel):
    simulated: StrictBool


@router.post("/api/merchant/payments/authorizations/{authorization_id}/fulfillment")
def fulfillment(authorization_id: str, body: FulfillmentRequest, authorization: str | None = Header(default=None)):
    from .integrated_capture import fulfill
    return fulfill(authorization_id, authorization, body.simulated)


def require_merchant(authorization: str | None):
    if os.getenv("B4_ENABLED", "").lower() == "true":
        raise HTTPException(404, "Not found")
    require_harness()
    if os.getenv("B3_CAPTURE_ENABLED", "").lower() != "true":
        raise HTTPException(404, "Not found")
    expected = os.getenv("B3_MERCHANT_TOKEN", "")
    if len(expected) < 32 or not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Merchant authentication required")
    if not hmac.compare_digest(authorization[7:].encode(), expected.encode()):
        raise HTTPException(401, "Merchant authentication required")


@router.post("/api/merchant/payments/authorizations/{authorization_id}/capture")
def capture(authorization_id: str, authorization: str | None = Header(default=None), x_b3_simulate_lost_response: str | None = Header(default=None), x_b5_simulate_lost_response: str | None = Header(default=None)):
    if os.getenv("B4_ENABLED", "").lower() == "true":
        from .integrated_capture import capture as integrated_capture
        return integrated_capture(authorization_id, authorization, x_b5_simulate_lost_response)
    require_merchant(authorization)
    with database() as conn:
        auth = conn.execute(
            "SELECT * FROM payment_operations WHERE operation_type = 'authorize' AND status = 'succeeded' AND paypal_authorization_id = %s FOR UPDATE",
            (authorization_id,),
        ).fetchone()
        if not auth:
            raise HTTPException(404, "Authorization not found")
        operation = conn.execute(
            "SELECT * FROM payment_operations WHERE quote_id = %s AND operation_type = 'capture'", (auth["quote_id"],)
        ).fetchone()
        if not operation:
            operation_id = uuid4().hex
            operation = conn.execute(
                "INSERT INTO payment_operations (operation_id, quote_id, session_id, operation_type, status, amount_cents, currency, paypal_request_id, paypal_order_id, paypal_authorization_id) "
                "VALUES (%s, %s, %s, 'capture', 'pending', %s, %s, %s, %s, %s) RETURNING *",
                (operation_id, auth["quote_id"], auth["session_id"], auth["amount_cents"], auth["currency"], operation_id, auth["paypal_order_id"], authorization_id),
            ).fetchone()
        operation_id = operation["operation_id"]

    # Lock across the provider call to serialize concurrent retries. The durable
    # operation was committed above, so a process crash cannot create a new ID.
    result = None
    with database() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("b3-capture:" + operation_id,))
        operation = conn.execute(
            "SELECT *, created_at > clock_timestamp() - interval '1 hour' AS retry_allowed FROM payment_operations WHERE operation_id = %s FOR UPDATE", (operation_id,)
        ).fetchone()
        if operation["status"] == "succeeded":
            return {"status": "captured", "capture_id": operation["paypal_capture_id"]}
        if operation["status"] not in ("pending", "unknown") or not operation["retry_allowed"]:
            raise HTTPException(409, "Capture requires manual reconciliation")
        try:
            result = provider.capture_authorization(authorization_id, operation["amount_cents"], operation["paypal_request_id"])
            amount = result.get("amount", {})
            expected_amount = f"{operation['amount_cents'] // 100}.{operation['amount_cents'] % 100:02d}"
            capture_id = result.get("id")
            if (not isinstance(capture_id, str) or not capture_id or result.get("status") != "COMPLETED"
                    or amount.get("currency_code") != "USD" or amount.get("value") != expected_amount):
                raise provider.ProviderError("Capture response requires reconciliation")
            # Test only: deliberately discard a confirmed response to exercise
            # recovery with the same stored request ID. Never enabled by default.
            if os.getenv("B3_ALLOW_FAULT_INJECTION", "").lower() == "true" and x_b3_simulate_lost_response == "true":
                raise provider.ProviderError("Simulated lost response")
        except (provider.ProviderError, AttributeError, TypeError):
            conn.execute("UPDATE payment_operations SET status = 'unknown', updated_at = clock_timestamp() WHERE operation_id = %s", (operation_id,))
            result = None
        else:
            conn.execute("UPDATE payment_operations SET status = 'succeeded', paypal_capture_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s", (capture_id, operation_id))
    if result is None:
        raise HTTPException(503, "Capture outcome unknown; retry the same authorization within one hour")
    return {"status": "captured", "capture_id": capture_id}


@router.post("/api/merchant/payments/quotes/{quote_id}/reconcile/{operation_type}")
def reconcile(quote_id: str, operation_type: str, authorization: str | None = Header(default=None)):
    """Retry an uncertain operation using its original persisted request ID."""
    if os.getenv("B4_ENABLED", "").lower() == "true":
        from .integrated import reconcile as integrated_reconcile
        return integrated_reconcile(quote_id, operation_type, authorization)
    require_merchant(authorization)
    if operation_type not in {"order", "authorize"}:
        raise HTTPException(404, "Not found")
    result = None
    with database() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("b3-reconcile:" + quote_id + ":" + operation_type,))
        row = conn.execute(
            "SELECT *, created_at > clock_timestamp() - interval '1 hour' AS retry_allowed, created_at < clock_timestamp() - interval '1 minute' AS recovery_ready FROM payment_operations WHERE quote_id = %s AND operation_type = %s FOR UPDATE",
            (quote_id, operation_type),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Operation not found")
        if row["status"] == "succeeded":
            return {"status": "succeeded", "order_id": row["paypal_order_id"], "authorization_id": row["paypal_authorization_id"]}
        if row["status"] not in {"pending", "unknown"} or not row["retry_allowed"]:
            raise HTTPException(409, "Operation requires manual reconciliation")
        if not row["recovery_ready"]:
            raise HTTPException(409, "Wait one minute before reconciling this operation")
        try:
            if operation_type == "order":
                reply = provider.create_order(row["amount_cents"], row["paypal_request_id"])
                provider_id = reply.get("id")
                if not isinstance(provider_id, str) or not provider_id:
                    raise provider.ProviderError("Invalid order response")
                conn.execute("UPDATE payment_operations SET status = 'succeeded', paypal_order_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s", (provider_id, row["operation_id"]))
                result = {"status": "succeeded", "order_id": provider_id, "authorization_id": None}
            else:
                if not row["paypal_order_id"]:
                    raise provider.ProviderError("Missing order ID")
                reply = provider.authorize_order(row["paypal_order_id"], row["paypal_request_id"])
                units = reply.get("purchase_units", [])
                auths = units[0].get("payments", {}).get("authorizations", []) if len(units) == 1 else []
                auth = auths[0] if len(auths) == 1 else {}
                amount = auth.get("amount", {})
                expected = f"{row['amount_cents'] // 100}.{row['amount_cents'] % 100:02d}"
                provider_id = auth.get("id")
                if (auth.get("status") != "CREATED" or not isinstance(provider_id, str) or not provider_id
                        or amount.get("currency_code") != "USD" or amount.get("value") != expected):
                    raise provider.ProviderError("Invalid authorization response")
                conn.execute("UPDATE payment_operations SET status = 'succeeded', paypal_authorization_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s", (provider_id, row["operation_id"]))
                result = {"status": "succeeded", "order_id": row["paypal_order_id"], "authorization_id": provider_id}
        except (provider.ProviderError, AttributeError, TypeError, IndexError):
            conn.execute("UPDATE payment_operations SET status = 'unknown', updated_at = clock_timestamp() WHERE operation_id = %s", (row["operation_id"],))
    if result is None:
        raise HTTPException(503, "Provider outcome remains unknown; retry the same operation within one hour")
    return result
