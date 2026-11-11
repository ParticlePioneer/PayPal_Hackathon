"""A2 in-memory negotiation and eligibility checks; never issues a quote."""

import time
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import Field, ValidationError, computed_field, model_validator

from .agent_process import call_agent_bounded
from .contracts import (
    ACTION_ADAPTER, AcceptAction, AskAction, BuyerAgentInput, BuyerPrivateInput,
    CalendarDate, Contract, CounterAction, DeclineAction, OfferAction, OfferTerms,
    PositiveInt, PublicEvent, PublicMessage, SellerAgentInput, SellerPrivateInput,
    SharedNegotiationContext,
)
from .model_client import ModelCallError


class NegotiationScenario(Contract):
    """Server-only container; never pass this object to either model."""

    buyer: BuyerPrivateInput = Field(repr=False)
    seller: SellerPrivateInput = Field(repr=False)

    @model_validator(mode="after")
    def matching_sku(self) -> Self:
        if self.buyer.requirements.sku != self.seller.sku:
            raise ValueError("Buyer and seller SKU must match")
        return self


class NegotiationLimits(Contract):
    max_turns: Annotated[int, Field(strict=True, ge=1, le=6)] = 6
    turn_timeout_ms: Annotated[int, Field(strict=True, ge=100, le=60000)] = 30000
    total_timeout_ms: Annotated[int, Field(strict=True, ge=100, le=360000)] = 120000


class ConstraintIssue(Contract):
    code: Literal["quantity_mismatch", "color_unavailable", "deadline_unavailable", "stock_unavailable", "price_unacceptable"]
    deliver_by: CalendarDate | None = None
    shortfall_qty: PositiveInt | None = None

    @computed_field
    @property
    def message(self) -> str:
        if self.code in {"deadline_unavailable", "stock_unavailable"} and self.deliver_by and self.shortfall_qty:
            return f"At least {self.shortfall_qty} more shirts are required by {self.deliver_by.isoformat()}."
        return {
            "quantity_mismatch": "The offer does not cover the requested quantity.",
            "color_unavailable": "The offer includes a color the buyer does not allow.",
            "deadline_unavailable": "The offer misses a delivery requirement.",
            "stock_unavailable": "The proposed delivery is not supported by available stock.",
            "price_unacceptable": "The price does not satisfy both parties' private constraints.",
        }[self.code]


def assess_offer(terms: OfferTerms, scenario: NegotiationScenario) -> tuple[ConstraintIssue, ...]:
    """Validate both parties' constraints against a read-only stock snapshot.

    Price failures intentionally reveal neither threshold nor which party's
    threshold failed. Stock is never reserved or changed by this function.
    """
    terms = OfferTerms.model_validate(terms)
    scenario = NegotiationScenario.model_validate(scenario)
    buyer, seller = scenario.buyer, scenario.seller
    requirements = buyer.requirements
    issues = []
    if sum(line.qty for line in terms.lines) != requirements.quantity:
        issues.append(ConstraintIssue(code="quantity_mismatch"))
    if any(line.color not in requirements.allowed_colors for line in terms.lines):
        issues.append(ConstraintIssue(code="color_unavailable"))
    if not seller.policy.minimum_total_cents <= terms.total_cents <= buyer.budget_cents:
        issues.append(ConstraintIssue(code="price_unacceptable"))
    for minimum in requirements.minimum_by_date:
        delivered = sum(line.qty for line in terms.lines if line.deliver_by <= minimum.date)
        if delivered < minimum.qty:
            issues.append(ConstraintIssue(code="deadline_unavailable", deliver_by=minimum.date, shortfall_qty=minimum.qty - delivered))
    # Cumulative per-color availability prevents reusing a batch across lines.
    for color in sorted({line.color for line in terms.lines}):
        for deadline in sorted({line.deliver_by for line in terms.lines if line.color == color}):
            needed = sum(line.qty for line in terms.lines if line.color == color and line.deliver_by <= deadline)
            available = sum(batch.available_qty for batch in seller.stock_batches if batch.color == color and batch.deliver_by <= deadline)
            if needed > available:
                issues.append(ConstraintIssue(code="stock_unavailable", deliver_by=deadline, shortfall_qty=needed - available))
    return tuple(issues)


def supply_shortfalls(scenario: NegotiationScenario) -> tuple[ConstraintIssue, ...]:
    """Public fixture explanation without batch IDs or a raw inventory snapshot."""
    requirements = scenario.buyer.requirements
    issues = []
    for minimum in requirements.minimum_by_date:
        available = sum(batch.available_qty for batch in scenario.seller.stock_batches
                        if batch.color in requirements.allowed_colors and batch.deliver_by <= minimum.date)
        if available < minimum.qty:
            issues.append(ConstraintIssue(code="stock_unavailable", deliver_by=minimum.date, shortfall_qty=minimum.qty - available))
    return tuple(issues)


_REASONS = {
    "agreed": "Both agents agreed to eligible terms. Stock is not reserved; checkout is unavailable.",
    "declined": "An agent declined the negotiation.",
    "ineligible_offer": "The proposed terms cannot be accepted.",
    "invalid_action": "An invalid agent action was rejected.",
    "turn_limit": "No agreement was reached within the turn limit.",
    "timeout": "The negotiation exceeded its time limit.",
    "model_error": "The model call failed; no agreement was created.",
}


class NegotiationResult(Contract):
    status: Literal["agreed", "no_deal", "retryable_error", "error"]
    reason_code: Literal["agreed", "declined", "ineligible_offer", "invalid_action", "turn_limit", "timeout", "model_error"]
    turns: Annotated[int, Field(strict=True, ge=0, le=6)]
    events: tuple[PublicEvent, ...] = ()
    issues: tuple[ConstraintIssue, ...] = ()
    agreement: OfferTerms | None = None
    quote: Literal[None] = None

    @computed_field
    @property
    def reason(self) -> str:
        return _REASONS[self.reason_code]

    @computed_field
    @property
    def messages(self) -> tuple[PublicMessage, ...]:
        return tuple(PublicMessage(event=event) for event in self.events)

    @model_validator(mode="after")
    def coherent_result(self) -> Self:
        if (self.status == "agreed") != (self.agreement is not None):
            raise ValueError("Only an agreed result contains agreement terms")
        if (self.status == "agreed") != (self.reason_code == "agreed"):
            raise ValueError("Agreement status and reason must match")
        if self.status == "agreed" and self.issues:
            raise ValueError("An agreed result cannot contain constraint failures")
        if len(self.events) > self.turns:
            raise ValueError("Saved actions cannot exceed attempted turns")
        return self


def run_negotiation(scenario: NegotiationScenario, source, limits: NegotiationLimits | None = None) -> NegotiationResult:
    """Alternating buyer/seller calls, at most six total, fresh state each run.

    Every new proposal replaces the active proposal. Accept/counter/targeted
    decline must reference the active opposite-party proposal. A proposer may
    counter its own active offer after the opponent asks for a revised offer.
    A proposal binds its proposer; acceptance never rewrites it. Eligibility is checked by the
    server before an acceptance event is published.
    """
    scenario = NegotiationScenario.model_validate(scenario)
    limits = NegotiationLimits.model_validate(NegotiationLimits() if limits is None else limits)
    deadline = time.monotonic() + limits.total_timeout_ms / 1000
    events = []
    active = None
    last_issues = ()

    def result(status, reason, turns, *, agreement=None, issues=None):
        return NegotiationResult(status=status, reason_code=reason, turns=turns, events=tuple(events),
                                 agreement=agreement, issues=last_issues if issues is None else issues)

    for turn in range(1, limits.max_turns + 1):
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            return result("retryable_error", "timeout", turn - 1)
        actor = "buyer" if turn % 2 else "seller"
        shared = SharedNegotiationContext(requirements=scenario.buyer.requirements, events=tuple(events))
        agent_input = (BuyerAgentInput(private=scenario.buyer, shared=shared) if actor == "buyer"
                       else SellerAgentInput(private=scenario.seller, shared=shared))
        timeout_ms = min(remaining_ms, limits.turn_timeout_ms)
        call_start = time.monotonic()
        try:
            action = call_agent_bounded(source, actor, agent_input, timeout_ms)
            action = ACTION_ADAPTER.validate_python(action)
        except ModelCallError as error:
            if error.code == "timeout":
                return result("retryable_error", "timeout", turn)
            if error.code == "invalid_response":
                return result("error", "invalid_action", turn)
            return result("retryable_error" if error.retryable else "error", "model_error", turn)
        except ValidationError:
            return result("error", "invalid_action", turn)
        except Exception:
            return result("error", "model_error", turn)
        if time.monotonic() >= deadline or (time.monotonic() - call_start) * 1000 >= timeout_ms:
            return result("retryable_error", "timeout", turn)
        targeted = isinstance(action, (AcceptAction, CounterAction)) or (isinstance(action, DeclineAction) and action.offer_id is not None)
        requested_revision = (
            isinstance(action, CounterAction) and bool(events)
            and isinstance(events[-1].action, AskAction)
            and events[-1].action.topic == "revised_offer" and events[-1].actor != actor
        )
        if targeted and (active is None or action.offer_id != active.issued_offer_id
                         or (active.actor == actor and not requested_revision)):
            return result("error", "invalid_action", turn)
        if isinstance(action, OfferAction) and active is not None:
            return result("error", "invalid_action", turn)
        if isinstance(action, AcceptAction):
            issues = assess_offer(active.action.terms, scenario)
            if issues:
                return result("no_deal", "ineligible_offer", turn, issues=issues)
        proposing = isinstance(action, (OfferAction, CounterAction))
        event = PublicEvent(event_id="e_" + uuid4().hex, sequence=len(events) + 1, actor=actor,
                            action=action, issued_offer_id="o_" + uuid4().hex if proposing else None)
        events.append(event)
        if proposing:
            active = event
            last_issues = assess_offer(action.terms, scenario)
        elif isinstance(action, AcceptAction):
            return result("agreed", "agreed", turn, agreement=active.action.terms, issues=())
        elif isinstance(action, DeclineAction):
            return result("no_deal", "declined", turn, issues=supply_shortfalls(scenario) or last_issues)
    return result("no_deal", "turn_limit", limits.max_turns)
