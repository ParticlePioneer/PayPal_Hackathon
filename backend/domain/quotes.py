"""A3 PostgreSQL inventory, reserved quotes, and server-side H0 adapter.

This module never calls a payment provider. commit_allocation/release_claim
are trusted server-only callbacks for confirmed outcomes, never public routes.
"""

from datetime import timedelta
from hashlib import sha256
import json
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import AwareDatetime, Field, TypeAdapter, ValidationError
from psycopg.types.json import Jsonb

from .contracts import (
    AcceptAction, Contract, OfferAction, CounterAction, OfferLine, OfferReference,
    SellerStockBatch, SharedNegotiationContext,
)
from .database import DomainDatabase, DomainError
from .negotiation import NegotiationResult, NegotiationScenario, assess_offer


_ID = TypeAdapter(OfferReference)
_MAX_BIGINT = 9223372036854775807


def _identifier(value):
    try:
        return _ID.validate_python(value)
    except ValidationError:
        raise DomainError("invalid_input") from None


class ReservedQuote(Contract):
    id: OfferReference
    session: OfferReference = Field(exclude=True, repr=False)
    currency: Literal["USD"]
    total_cents: int = Field(strict=True, gt=0, le=_MAX_BIGINT)
    expires_at: AwareDatetime
    lines: Annotated[tuple[OfferLine, ...], Field(min_length=1)]
    state: Literal["reserved", "claimed", "allocated", "expired", "released"]


def _view(row):
    return ReservedQuote(id=row["id"], session=row["session_id"], currency=row["currency"],
                         total_cents=row["total_cents"], expires_at=row["expires_at"],
                         lines=row["lines"], state=row["state"])


def _advisory(connection, namespace, identifier):
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (namespace + ":" + identifier,))


def _now(connection):
    # clock_timestamp(), unlike CURRENT_TIMESTAMP, advances while waiting on locks.
    return connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"]


def _quote(connection, quote_id, session=None):
    row = connection.execute("SELECT * FROM domain_quotes WHERE id = %s FOR UPDATE", (quote_id,)).fetchone()
    if row is None or (session is not None and row["session_id"] != session):
        raise DomainError("not_found")
    return row


def _hold_rows(connection, quote_id):
    return connection.execute(
        "SELECT b.*, r.qty AS held_qty FROM domain_reservations r "
        "JOIN domain_stock_batches b ON b.id = r.batch_id "
        "WHERE r.quote_id = %s ORDER BY b.id FOR UPDATE OF b", (quote_id,),
    ).fetchall()


def _change_hold(connection, row, *, allocate=False):
    holds = _hold_rows(connection, row["id"])
    if not holds:
        raise DomainError("stock_conflict")
    for batch in holds:
        updated = connection.execute(
            "UPDATE domain_stock_batches SET reserved_qty = reserved_qty - %s, "
            "allocated_qty = allocated_qty + %s WHERE id = %s AND reserved_qty >= %s RETURNING id",
            (batch["held_qty"], batch["held_qty"] if allocate else 0, batch["id"], batch["held_qty"]),
        ).fetchone()
        if updated is None:
            raise DomainError("stock_conflict")


def _expire_locked(connection, row):
    if row["state"] == "reserved" and row["expires_at"] <= _now(connection):
        _change_hold(connection, row)
        connection.execute("UPDATE domain_quotes SET state = 'expired' WHERE id = %s", (row["id"],))
        row["state"] = "expired"
    return row


def _unavailable(row):
    if row["state"] == "expired":
        return DomainError("expired")
    if row["state"] == "released":
        return DomainError("operation_conflict")
    return None


def _agreed_terms(outcome, scenario):
    try:
        outcome = NegotiationResult.model_validate(outcome)
        scenario = NegotiationScenario.model_validate(scenario)
        SharedNegotiationContext(requirements=scenario.buyer.requirements, events=outcome.events)
        if outcome.status != "agreed" or not outcome.events:
            raise ValueError("No agreement")
        last = outcome.events[-1]
        proposal = next((event for event in reversed(outcome.events[:-1])
                         if isinstance(event.action, (OfferAction, CounterAction))), None)
        if (not isinstance(last.action, AcceptAction) or proposal is None
                or last.action.offer_id != proposal.issued_offer_id or last.actor == proposal.actor
                or outcome.agreement != proposal.action.terms or assess_offer(outcome.agreement, scenario)
                or outcome.agreement.total_cents > _MAX_BIGINT
                or sum(line.qty for line in outcome.agreement.lines) > _MAX_BIGINT):
            raise ValueError("Ineligible agreement")
        return outcome.agreement, scenario
    except (ValidationError, ValueError, TypeError):
        raise DomainError("invalid_agreement") from None


class QuoteAdapter:
    """H0 methods match B's substitute; construct with a configured database.

    Successful claims remain held after quote expiry. Releasing a pending claim
    cancels the entire quote and restores stock once; obtaining another quote
    requires renegotiation, not a new operation against the cancelled quote.
    """

    def __init__(self, database: DomainDatabase):
        self.database = database

    def add_stock_batch(self, sku, batch: SellerStockBatch):
        sku = _identifier(sku)
        try:
            batch = SellerStockBatch.model_validate(batch)
        except ValidationError:
            raise DomainError("invalid_input") from None
        if batch.available_qty > _MAX_BIGINT:
            raise DomainError("invalid_input")
        with self.database.transaction() as connection:
            _advisory(connection, "domain-stock", batch.batch_id)
            existing = connection.execute("SELECT * FROM domain_stock_batches WHERE id = %s FOR UPDATE", (batch.batch_id,)).fetchone()
            expected = (sku, batch.color, batch.deliver_by, batch.available_qty)
            if existing:
                if (existing["sku"], existing["color"], existing["arrives_on"], existing["total_qty"]) != expected:
                    raise DomainError("stock_conflict")
                return  # Never reset reservation/allocation counters on a repeat seed.
            connection.execute("INSERT INTO domain_stock_batches (id, sku, color, arrives_on, total_qty) VALUES (%s, %s, %s, %s, %s)",
                               (batch.batch_id, *expected))

    def inventory_snapshot(self, sku) -> tuple[SellerStockBatch, ...]:
        """Server-private availability, not a public transcript projection."""
        sku = _identifier(sku)
        with self.database.transaction() as connection:
            rows = connection.execute("SELECT * FROM domain_stock_batches WHERE sku = %s ORDER BY id", (sku,)).fetchall()
        return tuple(SellerStockBatch(batch_id=row["id"], color=row["color"], deliver_by=row["arrives_on"],
                                     available_qty=row["total_qty"] - row["reserved_qty"] - row["allocated_qty"]) for row in rows)

    def issue_quote(self, session, outcome: NegotiationResult, scenario: NegotiationScenario, issuance_id, *, ttl_seconds=900) -> ReservedQuote:
        session, issuance_id = _identifier(session), _identifier(issuance_id)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise DomainError("invalid_input")
        terms, scenario = _agreed_terms(outcome, scenario)
        sku = scenario.buyer.requirements.sku
        fingerprint = sha256(json.dumps({"sku": sku, "terms": terms.model_dump(mode="json")}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        error = None
        with self.database.transaction() as connection:
            _advisory(connection, "domain-issue", issuance_id)
            existing = connection.execute("SELECT * FROM domain_quotes WHERE issuance_key = %s FOR UPDATE", (issuance_id,)).fetchone()
            if existing:
                if existing["session_id"] != session:
                    raise DomainError("not_found")
                if existing["request_fingerprint"] != fingerprint:
                    raise DomainError("idempotency_conflict")
                row = _expire_locked(connection, existing)
                error = _unavailable(row)
            else:
                # All SKU rows are locked in consistent ID order before any stock
                # mutation. Read-committed FOR UPDATE sees a competing winner's
                # updated counters after it releases those locks.
                batches = connection.execute("SELECT * FROM domain_stock_batches WHERE sku = %s ORDER BY id FOR UPDATE", (sku,)).fetchall()
                held = {}
                for line in sorted(terms.lines, key=lambda value: (value.deliver_by, value.color)):
                    remaining = line.qty
                    for batch in sorted(batches, key=lambda value: (value["arrives_on"], value["id"])):
                        if batch["color"] != line.color or batch["arrives_on"] > line.deliver_by:
                            continue
                        free = batch["total_qty"] - batch["reserved_qty"] - batch["allocated_qty"]
                        take = min(remaining, free)
                        if take:
                            connection.execute("UPDATE domain_stock_batches SET reserved_qty = reserved_qty + %s WHERE id = %s", (take, batch["id"]))
                            batch["reserved_qty"] += take
                            held[batch["id"]] = held.get(batch["id"], 0) + take
                            remaining -= take
                        if remaining == 0:
                            break
                    if remaining:
                        # The transaction rolls back all earlier batch updates.
                        raise DomainError("stock_conflict")
                created = _now(connection)
                quote_id = "q_" + uuid4().hex
                row = connection.execute(
                    "INSERT INTO domain_quotes (id, session_id, sku, issuance_key, request_fingerprint, currency, total_cents, lines, state, created_at, expires_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'reserved', %s, %s) RETURNING *",
                    (quote_id, session, sku, issuance_id, fingerprint, terms.currency, terms.total_cents,
                     Jsonb(terms.model_dump(mode="json")["lines"]), created, created + timedelta(seconds=ttl_seconds)),
                ).fetchone()
                for batch_id, qty in sorted(held.items()):
                    connection.execute("INSERT INTO domain_reservations (quote_id, batch_id, qty) VALUES (%s, %s, %s)", (quote_id, batch_id, qty))
        # Raise after the transaction commits expiry recovery, not from inside it.
        if error:
            raise error
        return _view(row)

    def get_quote(self, session, id) -> ReservedQuote:
        session, id = _identifier(session), _identifier(id)
        with self.database.transaction() as connection:
            row = _expire_locked(connection, _quote(connection, id, session))
            error = _unavailable(row)
        if error:
            raise error
        return _view(row)

    def claim_for_authorization(self, session, id, operation_id) -> ReservedQuote:
        session, id, operation_id = _identifier(session), _identifier(id), _identifier(operation_id)
        error = None
        with self.database.transaction() as connection:
            _advisory(connection, "domain-operation", operation_id)
            row = _quote(connection, id, session)
            previous = connection.execute("SELECT * FROM domain_authorization_claims WHERE operation_id = %s", (operation_id,)).fetchone()
            if previous:
                if previous["quote_id"] != id or previous["state"] == "released":
                    raise DomainError("operation_conflict")
                expected = "allocated" if previous["state"] == "committed" else "claimed"
                if row["state"] != expected:
                    raise DomainError("operation_conflict")
            else:
                if row["state"] == "expired":
                    raise DomainError("expired")
                if row["state"] != "reserved":
                    raise DomainError("operation_conflict")
                holds = _hold_rows(connection, id)
                if not holds or any(batch["reserved_qty"] < batch["held_qty"] for batch in holds):
                    raise DomainError("stock_conflict")
                # Check real time only after waiting on both quote and stock locks.
                row = _expire_locked(connection, row)
                error = _unavailable(row)
                if not error:
                    connection.execute("INSERT INTO domain_authorization_claims (operation_id, quote_id, state) VALUES (%s, %s, 'pending')", (operation_id, id))
                    connection.execute("UPDATE domain_quotes SET state = 'claimed' WHERE id = %s", (id,))
                    row["state"] = "claimed"
        if error:
            raise error
        return _view(row)

    def commit_allocation(self, operation_id):
        self._finish_claim(operation_id, commit=True)

    def release_claim(self, operation_id):
        self._finish_claim(operation_id, commit=False)

    def _finish_claim(self, operation_id, *, commit):
        operation_id = _identifier(operation_id)
        with self.database.transaction() as connection:
            _advisory(connection, "domain-operation", operation_id)
            claim = connection.execute("SELECT * FROM domain_authorization_claims WHERE operation_id = %s", (operation_id,)).fetchone()
            if claim is None:
                raise DomainError("not_found")
            row = _quote(connection, claim["quote_id"])
            if claim["state"] == "committed":
                return  # Release after commit must never restore allocated stock.
            if claim["state"] == "released":
                if commit:
                    raise DomainError("operation_conflict")
                return
            if row["state"] != "claimed":
                raise DomainError("operation_conflict")
            _change_hold(connection, row, allocate=commit)
            state = "allocated" if commit else "expired" if row["expires_at"] <= _now(connection) else "released"
            connection.execute("UPDATE domain_quotes SET state = %s WHERE id = %s", (state, row["id"]))
            connection.execute("UPDATE domain_authorization_claims SET state = %s WHERE operation_id = %s", ("committed" if commit else "released", operation_id))

    def release_quote(self, session, id):
        """Cancel only an unclaimed quote. Never use to resolve unknown payment."""
        session, id = _identifier(session), _identifier(id)
        with self.database.transaction() as connection:
            row = _quote(connection, id, session)
            if row["state"] in {"released", "expired"}:
                return
            if row["state"] != "reserved":
                raise DomainError("operation_conflict")
            _change_hold(connection, row)
            state = "expired" if row["expires_at"] <= _now(connection) else "released"
            connection.execute("UPDATE domain_quotes SET state = %s WHERE id = %s", (state, id))

    def recover_expired(self, *, limit=100) -> int:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise DomainError("invalid_input")
        recovered = 0
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM domain_quotes WHERE state = 'reserved' AND expires_at <= clock_timestamp() "
                "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED", (limit,),
            ).fetchall()
            for row in rows:
                _expire_locked(connection, row)
                recovered += 1
        return recovered
