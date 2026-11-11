"""A4 importable FastAPI router and durable negotiation service.

The host supplies trusted session identity, merchant policy, and agent source.
No app, provider, or synthetic seller policy is selected at import time.
"""

from typing import Callable
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, TypeAdapter, ValidationError
from psycopg.types.json import Jsonb

from .contracts import BuyerPrivateInput, BuyerRequirements, Contract, PublicEvent, PublicMessage, SellerPrivateInput
from .database import DomainError
from .negotiation import NegotiationResult, NegotiationScenario
from .quotes import QuoteAdapter, _identifier
from .turns import advance


class CreateNegotiation(BuyerRequirements):
    budget_cents: int = Field(strict=True, gt=0, le=9223372036854775807)


class TurnRequest(Contract):
    expected_version: int = Field(strict=True, ge=0, le=2147483647)


_EVENTS = TypeAdapter(tuple[PublicEvent, ...])


def _dump(value):
    return value.model_dump(mode="json", exclude=set(type(value).model_computed_fields))


class NegotiationService:
    def __init__(self, quotes: QuoteAdapter, seller_factory: Callable, agent_source, *, timeout_ms=30000):
        if type(timeout_ms) is not int or not 100 <= timeout_ms <= 60000:
            raise DomainError("invalid_input")
        self.quotes = quotes
        self.database = quotes.database
        self.seller_factory = seller_factory
        self.agent_source = agent_source
        self.timeout_ms = timeout_ms

    def _load(self, session, negotiation_id):
        session, negotiation_id = _identifier(session), _identifier(negotiation_id)
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM domain_negotiations WHERE id = %s AND session_id = %s", (negotiation_id, session)).fetchone()
        if row is None:
            raise DomainError("not_found")
        return row

    def create(self, session, payload: CreateNegotiation):
        session = _identifier(session)
        payload = CreateNegotiation.model_validate(payload)
        requirements = BuyerRequirements.model_validate(payload.model_dump(exclude={"budget_cents"}))
        buyer = BuyerPrivateInput(requirements=requirements, budget_cents=payload.budget_cents)
        # Policy/offer options originate from trusted server configuration.
        seller = SellerPrivateInput.model_validate(self.seller_factory(requirements))
        # Inventory is read from A3; caller-provided stock is never authoritative.
        seller = SellerPrivateInput(sku=seller.sku, policy=seller.policy, offer_options=seller.offer_options,
                                    stock_batches=self.quotes.inventory_snapshot(requirements.sku))
        scenario = NegotiationScenario(buyer=buyer, seller=seller)
        negotiation_id = "n_" + uuid4().hex
        with self.database.transaction() as connection:
            connection.execute("INSERT INTO domain_negotiations (id, session_id, status, scenario) VALUES (%s, %s, 'negotiating', %s)",
                               (negotiation_id, session, Jsonb(_dump(scenario))))
        return self.get(session, negotiation_id)

    def turn(self, session, negotiation_id, expected_version):
        request = TurnRequest(expected_version=expected_version)
        row = self._load(session, negotiation_id)
        if row["version"] != request.expected_version or row["status"] not in {"negotiating", "retryable_error"}:
            raise DomainError("operation_conflict")
        scenario = NegotiationScenario.model_validate(row["scenario"])
        events = _EVENTS.validate_python(row["events"])
        event, result = advance(scenario, self.agent_source, events, timeout_ms=self.timeout_ms)
        saved = events + ((event,) if event else ())
        status = ("negotiating" if result is None else "quoting" if result.status == "agreed"
                  else "no_deal" if result.status == "no_deal" else "retryable_error")
        reason = None if result is None else (result.issues[0].message if result.issues else result.reason)
        with self.database.transaction() as connection:
            updated = connection.execute(
                "UPDATE domain_negotiations SET version = version + 1, status = %s, events = %s, result = %s, reason = %s, updated_at = clock_timestamp() "
                "WHERE id = %s AND session_id = %s AND version = %s AND status IN ('negotiating', 'retryable_error') RETURNING id",
                (status, Jsonb([_dump(e) for e in saved]), Jsonb(_dump(result)) if result else None, reason, negotiation_id, session, request.expected_version),
            ).fetchone()
        if updated is None:
            raise DomainError("operation_conflict")
        view = self.get(session, negotiation_id)
        if result is not None and result.status == "agreed" and view["status"] == "no_deal":
            raise DomainError("stock_conflict")
        return view

    def _finish_quote(self, session, row):
        try:
            quote = self.quotes.issue_quote(session, NegotiationResult.model_validate(row["result"]),
                                            NegotiationScenario.model_validate(row["scenario"]), "issue_" + row["id"])
        except DomainError as error:
            if error.code not in {"stock_conflict", "expired"}:
                raise
            status = "expired" if error.code == "expired" else "no_deal"
            reason = "The quote has expired." if status == "expired" else "Stock is no longer available; please renegotiate."
            quote = None
        else:
            status, reason = "quoted", None
        with self.database.transaction() as connection:
            connection.execute("UPDATE domain_negotiations SET status = %s, quote_id = %s, reason = %s, updated_at = clock_timestamp() WHERE id = %s AND session_id = %s AND status = 'quoting'",
                               (status, quote.id if quote else None, reason, row["id"], session))

    def get(self, session, negotiation_id):
        row = self._load(session, negotiation_id)
        if row["status"] == "quoting":
            self._finish_quote(session, row)
            row = self._load(session, negotiation_id)
        quote = None
        status, reason = row["status"], row["reason"]
        if status == "quoted":
            try:
                q = self.quotes.get_quote(session, row["quote_id"])
                quote = q.model_dump(mode="json", exclude={"state"})
            except DomainError as error:
                if error.code != "expired":
                    raise
                status, reason = "expired", "The quote has expired."
                with self.database.transaction() as connection:
                    connection.execute("UPDATE domain_negotiations SET status = 'expired', reason = %s WHERE id = %s AND session_id = %s AND status = 'quoted'", (reason, negotiation_id, session))
        events = _EVENTS.validate_python(row["events"])
        return {"id": row["id"], "version": row["version"], "status": status,
                "messages": [PublicMessage(event=e).model_dump(mode="json") for e in events], "reason": reason, "quote": quote}


def trusted_session(request: Request):
    """The host must establish request.state.session_id using its own session middleware."""
    session = getattr(request.state, "session_id", None)
    if not isinstance(session, str) or not session:
        raise HTTPException(status_code=401, detail="A server-owned session is required.")
    return session


def create_router(service: NegotiationService, *, session_dependency=trusted_session):
    router = APIRouter(prefix="/api/negotiations", tags=["negotiations"])

    async def parse(request, cls):
        try:
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 131072:
                    raise ValueError("Input too large")
                body.extend(chunk)
            return cls.model_validate_json(bytes(body))
        except (ValidationError, ValueError):
            raise HTTPException(status_code=422, detail="Invalid negotiation input.") from None

    def invoke(fn):
        try:
            return fn()
        except DomainError as error:
            raise HTTPException(status_code=error.status_code, detail={"code": error.code, "message": str(error)}) from None

    @router.post("")
    async def create(request: Request, session: str = Depends(session_dependency)):
        payload = await parse(request, CreateNegotiation)
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(invoke, lambda: service.create(session, payload))

    @router.post("/{negotiation_id}/turn")
    async def turn(negotiation_id: str, request: Request, session: str = Depends(session_dependency)):
        payload = await parse(request, TurnRequest)
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(invoke, lambda: service.turn(session, negotiation_id, payload.expected_version))

    @router.get("/{negotiation_id}")
    def get(negotiation_id: str, session: str = Depends(session_dependency)):
        return invoke(lambda: service.get(session, negotiation_id))

    return router
