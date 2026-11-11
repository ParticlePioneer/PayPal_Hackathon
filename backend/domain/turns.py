"""One validated negotiation action for durable, versioned API turns."""

from uuid import uuid4

from pydantic import ValidationError

from .agent_process import call_agent_bounded
from .contracts import (
    ACTION_ADAPTER, AcceptAction, AskAction, BuyerAgentInput, CounterAction,
    DeclineAction, OfferAction, PublicEvent, SellerAgentInput, SharedNegotiationContext,
)
from .model_client import ModelCallError
from .negotiation import NegotiationResult, assess_offer, supply_shortfalls


def advance(scenario, source, events, *, timeout_ms=30000):
    """Return (event or None, result or None); only the selected role sees its private input."""
    events = tuple(events)
    turn = len(events) + 1
    if turn > 6:
        return None, NegotiationResult(status="no_deal", reason_code="turn_limit", turns=6, events=events)
    actor = "buyer" if turn % 2 else "seller"
    shared = SharedNegotiationContext(requirements=scenario.buyer.requirements, events=events)
    data = BuyerAgentInput(private=scenario.buyer, shared=shared) if actor == "buyer" else SellerAgentInput(private=scenario.seller, shared=shared)
    try:
        action = ACTION_ADAPTER.validate_python(call_agent_bounded(source, actor, data, timeout_ms))
    except ModelCallError as error:
        reason = "timeout" if error.code == "timeout" else "invalid_action" if error.code == "invalid_response" else "model_error"
        status = "retryable_error" if error.retryable else "error"
        return None, NegotiationResult(status=status, reason_code=reason, turns=turn, events=events)
    except (ValidationError, ValueError, TypeError):
        return None, NegotiationResult(status="error", reason_code="invalid_action", turns=turn, events=events)
    except Exception:
        return None, NegotiationResult(status="error", reason_code="model_error", turns=turn, events=events)
    active = next((event for event in reversed(events) if isinstance(event.action, (OfferAction, CounterAction))), None)
    targeted = isinstance(action, (AcceptAction, CounterAction)) or (isinstance(action, DeclineAction) and action.offer_id is not None)
    revision = (isinstance(action, CounterAction) and bool(events) and isinstance(events[-1].action, AskAction)
                and events[-1].action.topic == "revised_offer" and events[-1].actor != actor)
    if ((targeted and (active is None or action.offer_id != active.issued_offer_id or (active.actor == actor and not revision)))
            or (isinstance(action, OfferAction) and active is not None)):
        return None, NegotiationResult(status="error", reason_code="invalid_action", turns=turn, events=events)
    if isinstance(action, AcceptAction):
        issues = assess_offer(active.action.terms, scenario)
        if issues:
            return None, NegotiationResult(status="no_deal", reason_code="ineligible_offer", turns=turn, events=events, issues=issues)
    proposing = isinstance(action, (OfferAction, CounterAction))
    event = PublicEvent(event_id="e_" + uuid4().hex, sequence=turn, actor=actor, action=action,
                        issued_offer_id="o_" + uuid4().hex if proposing else None)
    saved = events + (event,)
    if isinstance(action, AcceptAction):
        return event, NegotiationResult(status="agreed", reason_code="agreed", turns=turn, events=saved, agreement=active.action.terms)
    if isinstance(action, DeclineAction):
        issues = supply_shortfalls(scenario) or (assess_offer(active.action.terms, scenario) if active else ())
        return event, NegotiationResult(status="no_deal", reason_code="declined", turns=turn, events=saved, issues=issues)
    if turn == 6:
        return event, NegotiationResult(status="no_deal", reason_code="turn_limit", turns=turn, events=saved)
    return event, None
