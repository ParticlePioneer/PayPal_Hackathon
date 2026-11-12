"""Integrated checkout, using domain-owned quotes and durable operations.

Uncertain operations stay pending for reconciliation. No provider request is
replayed here, and a pending domain claim is never released on a timeout.
"""
from uuid import uuid4
from contextlib import contextmanager
import hmac
import os

from fastapi import HTTPException, Request
from backend.domain.database import DomainDatabase, DomainError
from backend.domain.quotes import QuoteAdapter
from backend.payments import provider
from backend.payments.domain_handoff import PaymentUncertain, authorize_reserved_quote
from backend.payments.harness import database, same_origin


def session(request: Request) -> str:
    value = getattr(request.state, "session_id", None)
    if not value:
        raise HTTPException(401, "A server-owned session is required")
    return value


def adapter():
    return QuoteAdapter(DomainDatabase.from_environment())


def domain_error(error: DomainError):
    raise HTTPException(error.status_code, {"code": error.code, "message": str(error)}) from None


@contextmanager
def payment_lock(quote_id):
    """Hold one session lock across durable writes and provider calls for a quote."""
    key = "b5-payment:" + quote_id
    with database() as conn:
        locked = conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS acquired", (key,)).fetchone()
        if not locked or not locked["acquired"]:
            raise HTTPException(409, "Payment operation in progress; check status before retrying")
        try:
            yield
        finally:
            conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (key,))


def create_order(quote_id: str, request: Request):
    same_origin(request)
    session(request)
    with payment_lock(quote_id):
        return _create_order(quote_id, request)


def _create_order(quote_id: str, request: Request):
    same_origin(request)
    owner = session(request)
    quotes = adapter()
    operation = uuid4().hex
    try:
        with database() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("b4-order:" + quote_id,))
            quote = quotes.get_quote(owner, quote_id)
            if quote.state != "reserved":
                raise HTTPException(409, "Quote is not available for a new order")
            old = conn.execute("SELECT * FROM payment_operations WHERE quote_id = %s AND operation_type = 'order'", (quote_id,)).fetchone()
            if old:
                if old["session_id"] != owner:
                    raise HTTPException(404, "Quote not found")
                if old["status"] == "succeeded" and old["paypal_order_id"]:
                    return {"id": old["paypal_order_id"]}
                raise HTTPException(409, "Order outcome pending; do not start another checkout")
            conn.execute("INSERT INTO payment_operations (operation_id, quote_id, session_id, operation_type, status, amount_cents, currency, paypal_request_id) VALUES (%s, %s, %s, 'order', 'pending', %s, %s, %s)", (operation, quote_id, owner, quote.total_cents, quote.currency, operation))
    except DomainError as error:
        domain_error(error)
    try:
        response = provider.create_order(quote.total_cents, operation)
        order_id = response.get("id")
        if not isinstance(order_id, str) or not order_id:
            raise provider.ProviderError("Invalid order response")
    except provider.ProviderError:
        with database() as conn:
            conn.execute("UPDATE payment_operations SET status = 'unknown', updated_at = clock_timestamp() WHERE operation_id = %s AND status <> 'succeeded'", (operation,))
        raise HTTPException(503, "Order outcome unknown; do not start another checkout") from None
    with database() as conn:
        conn.execute("UPDATE payment_operations SET status = 'succeeded', paypal_order_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s", (order_id, operation))
    return {"id": order_id}


def order_quote(order_id, owner):
    with database() as conn:
        row = conn.execute("SELECT quote_id FROM payment_operations WHERE paypal_order_id = %s AND session_id = %s AND operation_type = 'order' AND status = 'succeeded'", (order_id, owner)).fetchone()
    if not row:
        raise HTTPException(404, "Order not found")
    return row["quote_id"]


def authorize(order_id: str, request: Request):
    same_origin(request)
    quote_id = order_quote(order_id, session(request))
    with payment_lock(quote_id):
        return _authorize(order_id, request)


def _authorize(order_id: str, request: Request):
    same_origin(request)
    owner = session(request)
    operation = uuid4().hex
    with database() as conn:
        order = conn.execute("SELECT * FROM payment_operations WHERE paypal_order_id = %s AND session_id = %s AND operation_type = 'order' AND status = 'succeeded' FOR UPDATE", (order_id, owner)).fetchone()
        if not order:
            raise HTTPException(404, "Order not found")
        previous = conn.execute("SELECT * FROM payment_operations WHERE quote_id = %s AND operation_type = 'authorize'", (order["quote_id"],)).fetchone()
        if previous:
            if previous["status"] == "succeeded" and previous["paypal_authorization_id"]:
                return {"status": "authorized", "authorization_id": previous["paypal_authorization_id"]}
            raise HTTPException(409, "Authorization pending; do not start another checkout")
        conn.execute("INSERT INTO payment_operations (operation_id, quote_id, session_id, operation_type, status, amount_cents, currency, paypal_request_id, paypal_order_id) VALUES (%s, %s, %s, 'authorize', 'pending', %s, %s, %s, %s)", (operation, order["quote_id"], owner, order["amount_cents"], order["currency"], operation, order_id))
    try:
        def save_verified(authorization_id):
            # Commit the verified provider ID before allocating inventory.
            with database() as conn:
                saved = conn.execute("UPDATE payment_operations SET paypal_authorization_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s AND status = 'pending' RETURNING operation_id", (authorization_id, operation)).fetchone()
                if not saved:
                    raise PaymentUncertain("Authorization record could not be updated")
        result = authorize_reserved_quote(adapter(), owner, order["quote_id"], operation, order_id, expected_cents=order["amount_cents"], on_verified=save_verified)
    except DomainError as error:
        with database() as conn:
            status = "unknown" if error.code == "storage_unavailable" else "failed"
            conn.execute("UPDATE payment_operations SET status = %s, updated_at = clock_timestamp() WHERE operation_id = %s AND status = 'pending'", (status, operation))
        domain_error(error)
    except PaymentUncertain:
        with database() as conn:
            conn.execute("UPDATE payment_operations SET status = 'unknown', updated_at = clock_timestamp() WHERE operation_id = %s AND status <> 'succeeded'", (operation,))
        raise HTTPException(503, "Authorization outcome unknown; do not start another checkout") from None
    with database() as conn:
        conn.execute("UPDATE payment_operations SET status = 'succeeded', paypal_authorization_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s", (result.authorization_id, operation))
    return {"status": "authorized", "authorization_id": result.authorization_id}


def payment_status(quote_id: str, request: Request):
    owner = session(request)
    # Check ownership even when no payment exists. Claimed/allocated quotes
    # remain readable by their owner in the domain adapter.
    try:
        adapter().get_quote(owner, quote_id)
    except DomainError as error:
        domain_error(error)
    with database() as conn:
        rows = conn.execute("SELECT operation_type, status, paypal_order_id, paypal_authorization_id, paypal_capture_id FROM payment_operations WHERE quote_id = %s AND session_id = %s ORDER BY created_at", (quote_id, owner)).fetchall()
    return {"quote_id": quote_id, "operations": rows}


def reconcile(quote_id: str, operation_type: str, authorization: str | None):
    secret = os.getenv("B4_MERCHANT_TOKEN", "")
    if (len(secret) < 32 or not authorization or not authorization.startswith("Bearer ")
            or not hmac.compare_digest(authorization[7:].encode(), secret.encode())):
        raise HTTPException(401, "Merchant authentication required")
    with payment_lock(quote_id):
        return _reconcile(quote_id, operation_type, authorization)


def _reconcile(quote_id: str, operation_type: str, authorization: str | None):
    """Merchant-only replay using the durable request ID and domain claim."""
    secret = os.getenv("B4_MERCHANT_TOKEN", "")
    if (len(secret) < 32 or not authorization or not authorization.startswith("Bearer ")
            or not hmac.compare_digest(authorization[7:].encode(), secret.encode())):
        raise HTTPException(401, "Merchant authentication required")
    if operation_type not in {"order", "authorize"}:
        raise HTTPException(404, "Operation not found")
    outcome = None
    with database() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("b4-reconcile:" + quote_id + ":" + operation_type,))
        row = conn.execute("SELECT *, created_at > clock_timestamp() - interval '1 hour' AS retry_allowed, created_at < clock_timestamp() - interval '1 minute' AS recovery_ready FROM payment_operations WHERE quote_id = %s AND operation_type = %s FOR UPDATE", (quote_id, operation_type)).fetchone()
        if not row:
            raise HTTPException(404, "Operation not found")
        if row["status"] == "succeeded":
            return {"status": "succeeded", "order_id": row["paypal_order_id"], "authorization_id": row["paypal_authorization_id"]}
        saved_authorization = operation_type == "authorize" and bool(row.get("paypal_authorization_id"))
        if row["status"] not in {"pending", "unknown"} or (not row["retry_allowed"] and not saved_authorization) or not row["recovery_ready"]:
            raise HTTPException(409, "Operation is not eligible for automatic reconciliation")
    # The session advisory lock remains held while separate transactions persist
    # provider identifiers and commit domain allocation. No row lock spans an
    # external request or a domain adapter connection.
    try:
        if operation_type == "order":
            quote = adapter().get_quote(row["session_id"], quote_id)
            if quote.total_cents != row["amount_cents"] or quote.currency != row["currency"] or quote.state != "reserved":
                raise PaymentUncertain("Quote is not available")
            reply = provider.create_order(row["amount_cents"], row["paypal_request_id"])
            order_id = reply.get("id")
            if not isinstance(order_id, str) or not order_id:
                raise PaymentUncertain("Invalid order response")
            with database() as conn:
                conn.execute("UPDATE payment_operations SET status = 'succeeded', paypal_order_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s", (order_id, row["operation_id"]))
            outcome = {"status": "succeeded", "order_id": order_id, "authorization_id": None}
        else:
            known_authorization = row.get("paypal_authorization_id")
            if known_authorization:
                adapter().claim_for_authorization(row["session_id"], quote_id, row["operation_id"])
                adapter().commit_allocation(row["operation_id"])
                authorization_id = known_authorization
            else:
                def save_verified(authorization_id):
                    with database() as conn:
                        saved = conn.execute("UPDATE payment_operations SET paypal_authorization_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s AND status IN ('pending', 'unknown') RETURNING operation_id", (authorization_id, row["operation_id"])).fetchone()
                        if not saved:
                            raise PaymentUncertain("Authorization record could not be updated")
                result = authorize_reserved_quote(adapter(), row["session_id"], quote_id, row["operation_id"], row["paypal_order_id"], expected_cents=row["amount_cents"], on_verified=save_verified)
                authorization_id = result.authorization_id
            with database() as conn:
                conn.execute("UPDATE payment_operations SET status = 'succeeded', paypal_authorization_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s", (authorization_id, row["operation_id"]))
            outcome = {"status": "succeeded", "order_id": row["paypal_order_id"], "authorization_id": authorization_id}
    except (DomainError, PaymentUncertain, provider.ProviderError, AttributeError, TypeError):
        with database() as conn:
            conn.execute("UPDATE payment_operations SET status = 'unknown', updated_at = clock_timestamp() WHERE operation_id = %s AND status <> 'succeeded'", (row["operation_id"],))
    if outcome is None:
        raise HTTPException(503, "Outcome remains unknown; keep the reservation held")
    return outcome
