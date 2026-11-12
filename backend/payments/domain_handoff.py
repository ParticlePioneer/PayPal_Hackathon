"""B4 domain/payment boundary. Call only with a persisted operation ID.

This module has no HTTP routes and must not be wired to buyers until the
payment operation is durably recorded and concurrent requests are serialized.
"""
from dataclasses import dataclass

from backend.domain.database import DomainError
from backend.payments import provider


class PaymentUncertain(Exception):
    """A claim is held and the provider result needs reconciliation."""


@dataclass(frozen=True)
class AuthorizationResult:
    authorization_id: str
    amount_cents: int


def authorize_reserved_quote(quotes, session_id: str, quote_id: str,
                             operation_id: str, order_id: str, *, expected_cents: int | None = None, on_verified=None) -> AuthorizationResult:
    """Claim first; never release after a potentially submitted provider call.

    The caller owns persistence, locking and ensuring the same operation ID is
    reused for every retry. It must persist the returned ID and expose a pending
    state if this function raises PaymentUncertain or persistence later fails.
    """
    quote = quotes.claim_for_authorization(session_id, quote_id, operation_id)
    if expected_cents is not None and quote.total_cents != expected_cents:
        raise PaymentUncertain("Saved order amount does not match the quote")
    try:
        response = provider.authorize_order(order_id, operation_id)
        units = response.get("purchase_units", [])
        authorizations = units[0].get("payments", {}).get("authorizations", []) if len(units) == 1 else []
        authorization = authorizations[0] if len(authorizations) == 1 else {}
        amount = authorization.get("amount", {})
        expected = f"{quote.total_cents // 100}.{quote.total_cents % 100:02d}"
        authorization_id = authorization.get("id")
        if (authorization.get("status") != "CREATED" or not isinstance(authorization_id, str)
                or not authorization_id or amount.get("currency_code") != quote.currency
                or amount.get("value") != expected):
            raise provider.ProviderError("Authorization response could not be verified")
    except (provider.ProviderError, AttributeError, TypeError, IndexError):
        raise PaymentUncertain("Authorization outcome requires reconciliation") from None
    if on_verified is not None:
        try:
            on_verified(authorization_id)
        except Exception:
            raise PaymentUncertain("Authorization persistence requires reconciliation") from None
    try:
        quotes.commit_allocation(operation_id)
    except DomainError:
        # PayPal may already have authorized; retain the claim for recovery.
        raise PaymentUncertain("Authorization allocation requires reconciliation") from None
    return AuthorizationResult(authorization_id, quote.total_cents)
