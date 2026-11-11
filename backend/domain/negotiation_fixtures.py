"""Explicitly simulated A2 agents and fixture scenarios; never live fallback."""

from .contracts import (
    AcceptAction, AskAction, DeclineAction, OfferAction, CounterAction,
    SellerPolicy, SellerPrivateInput, SellerStockBatch,
)
from .fixtures import buyer_fixture, split_offer_fixture
from .negotiation import NegotiationScenario


def fixture_scenario(minimum_total_cents: int, *, shortfall: bool = False) -> NegotiationScenario:
    """Requires an explicit caller-supplied floor, with no commercial default."""
    buyer = buyer_fixture()
    split = split_offer_fixture()
    return NegotiationScenario(
        buyer=buyer,
        seller=SellerPrivateInput(
            sku=buyer.requirements.sku, policy=SellerPolicy(minimum_total_cents=minimum_total_cents),
            stock_batches=(
                SellerStockBatch(batch_id="friday_navy", color="navy", available_qty=8 if shortfall else 12, deliver_by="2026-11-13"),
                SellerStockBatch(batch_id="monday_black", color="black", available_qty=18, deliver_by="2026-11-16"),
            ), offer_options=(split,),
        ),
    )


def _latest_offer(shared):
    return next((event for event in reversed(shared.events) if isinstance(event.action, (OfferAction, CounterAction))), None)


class FixtureAgents:
    """Deterministic development substitute. No model or payment calls."""

    def generate_buyer(self, agent_input):
        offered = _latest_offer(agent_input.shared)
        if offered is None:
            return AskAction(type="ask", topic="delivery_options")
        terms = offered.action.terms
        requirements = agent_input.private.requirements
        if terms.total_cents > agent_input.private.budget_cents:
            return DeclineAction(type="decline", reason_code="budget_infeasible", offer_id=offered.issued_offer_id)
        if any(line.color not in requirements.allowed_colors for line in terms.lines):
            return DeclineAction(type="decline", reason_code="color_unavailable", offer_id=offered.issued_offer_id)
        if any(sum(line.qty for line in terms.lines if line.deliver_by <= minimum.date) < minimum.qty for minimum in requirements.minimum_by_date):
            return DeclineAction(type="decline", reason_code="deadline_unavailable", offer_id=offered.issued_offer_id)
        return AcceptAction(type="accept", offer_id=offered.issued_offer_id)

    def generate_seller(self, agent_input):
        requirements = agent_input.shared.requirements
        if any(sum(batch.available_qty for batch in agent_input.private.stock_batches
                   if batch.color in requirements.allowed_colors and batch.deliver_by <= minimum.date) < minimum.qty
               for minimum in requirements.minimum_by_date):
            return DeclineAction(type="decline", reason_code="deadline_unavailable")
        offered = _latest_offer(agent_input.shared)
        if offered is not None:
            if offered.actor == "seller":
                return CounterAction(type="counter", offer_id=offered.issued_offer_id, terms=offered.action.terms)
            return AcceptAction(type="accept", offer_id=offered.issued_offer_id)
        if agent_input.private.offer_options:
            return OfferAction(type="offer", terms=agent_input.private.offer_options[0])
        return DeclineAction(type="decline", reason_code="terms_unacceptable")
