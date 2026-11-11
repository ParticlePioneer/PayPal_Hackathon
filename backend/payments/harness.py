"""B2 isolated USD 1 harness. Not a merchant-backed checkout implementation."""
import hashlib
import os
import re
import secrets
from contextlib import contextmanager
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel
from . import provider

router = APIRouter()
COOKIE = "b2_session"


def enabled():
    return os.getenv("B2_HARNESS_ENABLED", "").lower() == "true"


def require_harness():
    if not enabled():
        raise HTTPException(404, "Not found")


def session_id(token):
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise HTTPException(401, "Start a test checkout first")
    return hashlib.sha256(token.encode()).hexdigest()


def same_origin(request):
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if not origin or origin not in {f"https://{host}", f"http://{host}"}:
        raise HTTPException(403, "Invalid request origin")


@contextmanager
def database():
    try:
        with psycopg.connect(os.getenv("DATABASE_URL", ""), connect_timeout=10, row_factory=dict_row) as conn:
            yield conn
    except psycopg.Error:
        raise HTTPException(503, "Payment storage unavailable") from None


class OrderRequest(BaseModel):
    quote_id: str


@router.post("/api/test-checkout/session")
def start_session(request: Request, response: Response, b2_session: str | None = Cookie(default=None)):
    require_harness()
    same_origin(request)
    client_id = os.getenv("PAYPAL_CLIENT_ID", "")
    if not client_id:
        raise HTTPException(503, "PayPal Sandbox is not configured")
    # Reuse the same server-owned quote on refresh, including pending or unknown
    # outcomes. A fresh browser session is required for a separate test.
    if b2_session:
        owner = session_id(b2_session)
        with database() as conn:
            existing = conn.execute("SELECT id FROM payment_test_quotes WHERE session_id = %s ORDER BY created_at DESC LIMIT 1", (owner,)).fetchone()
        if existing:
            return {"quote_id": existing["id"], "client_id": client_id, "currency": "USD", "total_cents": 100}
    raw_session = secrets.token_urlsafe(32)
    owner = session_id(raw_session)
    quote_id = "test_" + uuid4().hex
    with database() as conn:
        conn.execute("INSERT INTO payment_test_quotes (id, session_id, expires_at) VALUES (%s, %s, clock_timestamp() + interval '15 minutes')", (quote_id, owner))
    response.set_cookie(COOKIE, raw_session, httponly=True, secure=bool(os.getenv("RENDER")), samesite="strict", path="/", max_age=86400)
    return {"quote_id": quote_id, "client_id": client_id, "currency": "USD", "total_cents": 100}


@router.post("/api/payments/orders")
def create_order(body: OrderRequest, request: Request, b2_session: str | None = Cookie(default=None)):
    require_harness()
    same_origin(request)
    owner = session_id(b2_session)
    operation = uuid4().hex
    with database() as conn:
        quote = conn.execute("SELECT expires_at > clock_timestamp() AS valid FROM payment_test_quotes WHERE id = %s AND session_id = %s FOR UPDATE", (body.quote_id, owner)).fetchone()
        if not quote:
            raise HTTPException(404, "Quote not found")
        if not quote["valid"]:
            raise HTTPException(410, "Quote expired")
        existing = conn.execute("SELECT status, paypal_order_id FROM payment_operations WHERE quote_id = %s AND operation_type = 'order'", (body.quote_id,)).fetchone()
        if existing:
            if existing["status"] == "succeeded" and existing["paypal_order_id"]:
                return {"id": existing["paypal_order_id"]}
            raise HTTPException(409, "Payment is pending; do not start another checkout")
        conn.execute("INSERT INTO payment_operations (operation_id, quote_id, session_id, operation_type, status, amount_cents, currency, paypal_request_id) VALUES (%s, %s, %s, 'order', 'pending', 100, 'USD', %s)", (operation, body.quote_id, owner, operation))
    try:
        result = provider.create_order(100, operation)
        order_id = result.get("id")
        if not isinstance(order_id, str) or not order_id:
            raise provider.ProviderError("Invalid order response")
    except provider.ProviderError:
        with database() as conn:
            conn.execute("UPDATE payment_operations SET status = 'unknown', updated_at = clock_timestamp() WHERE operation_id = %s", (operation,))
        raise HTTPException(503, "Order outcome unknown; do not retry with a new quote") from None
    with database() as conn:
        conn.execute("UPDATE payment_operations SET status = 'succeeded', paypal_order_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s", (order_id, operation))
    return {"id": order_id}


@router.post("/api/payments/orders/{order_id}/authorize")
def authorize(order_id: str, request: Request, b2_session: str | None = Cookie(default=None)):
    require_harness()
    same_origin(request)
    owner = session_id(b2_session)
    operation = uuid4().hex
    with database() as conn:
        order = conn.execute("SELECT * FROM payment_operations WHERE paypal_order_id = %s AND session_id = %s AND operation_type = 'order' AND status = 'succeeded' FOR UPDATE", (order_id, owner)).fetchone()
        if not order:
            raise HTTPException(404, "Order not found")
        old = conn.execute("SELECT status, paypal_authorization_id FROM payment_operations WHERE quote_id = %s AND operation_type = 'authorize'", (order["quote_id"],)).fetchone()
        if old:
            if old["status"] == "succeeded" and old["paypal_authorization_id"]:
                return {"status": "authorized", "authorization_id": old["paypal_authorization_id"]}
            raise HTTPException(409, "Authorization pending; do not retry with a new quote")
        valid = conn.execute("SELECT expires_at > clock_timestamp() AS valid FROM payment_test_quotes WHERE id = %s AND session_id = %s", (order["quote_id"], owner)).fetchone()
        if not valid or not valid["valid"]:
            raise HTTPException(410, "Quote expired")
        conn.execute("INSERT INTO payment_operations (operation_id, quote_id, session_id, operation_type, status, amount_cents, currency, paypal_request_id, paypal_order_id) VALUES (%s, %s, %s, 'authorize', 'pending', 100, 'USD', %s, %s)", (operation, order["quote_id"], owner, operation, order_id))
    try:
        result = provider.authorize_order(order_id, operation)
        units = result.get("purchase_units", [])
        auths = units[0].get("payments", {}).get("authorizations", []) if len(units) == 1 else []
        auth = auths[0] if len(auths) == 1 else {}
        amount = auth.get("amount", {})
        if auth.get("status") != "CREATED" or not isinstance(auth.get("id"), str) or not auth["id"] or amount.get("currency_code") != "USD" or amount.get("value") != "1.00":
            raise provider.ProviderError("Unexpected authorization response")
        auth_id = auth["id"]
    except (provider.ProviderError, AttributeError, TypeError, IndexError):
        with database() as conn:
            conn.execute("UPDATE payment_operations SET status = 'unknown', updated_at = clock_timestamp() WHERE operation_id = %s", (operation,))
        raise HTTPException(503, "Authorization outcome unknown; do not retry with a new quote") from None
    with database() as conn:
        conn.execute("UPDATE payment_operations SET status = 'succeeded', paypal_authorization_id = %s, updated_at = clock_timestamp() WHERE operation_id = %s", (auth_id, operation))
    return {"status": "authorized", "authorization_id": auth_id}


@router.get("/api/payments/quotes/{quote_id}")
def payment_status(quote_id: str, b2_session: str | None = Cookie(default=None)):
    require_harness()
    owner = session_id(b2_session)
    with database() as conn:
        exists = conn.execute("SELECT 1 FROM payment_test_quotes WHERE id = %s AND session_id = %s", (quote_id, owner)).fetchone()
        if not exists:
            raise HTTPException(404, "Quote not found")
        rows = conn.execute("SELECT operation_type, status, paypal_order_id, paypal_authorization_id FROM payment_operations WHERE quote_id = %s AND session_id = %s ORDER BY created_at", (quote_id, owner)).fetchall()
    return {"quote_id": quote_id, "operations": rows}
