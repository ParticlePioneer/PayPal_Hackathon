"""A5 six-case development comparison; no frozen data or results are modified.

Fixture mode is simulated and cannot establish AI performance. Live mode is
explicit and uses configured Gemini; no fixture fallback is used on errors.
"""

import argparse
import json
from pathlib import Path
import sys
import time

from .contracts import (
    AcceptAction, AskAction, BuyerPrivateInput, BuyerRequirements, DeclineAction,
    OfferAction, OfferLine, OfferTerms, SellerPolicy, SellerPrivateInput, SellerStockBatch,
)
from .openrouter_client import OpenRouterActionClient
from .openrouter_config import Settings as OpenRouterSettings
from .model_config import ModelConfigurationError
from .negotiation import NegotiationLimits, NegotiationScenario, assess_offer, run_negotiation
from .negotiation_fixtures import FixtureAgents, fixture_scenario
from . import negotiation
from .model_client import ModelCallError


def scenarios():
    """Public development cases; the merchant floors and stock are synthetic."""
    base = fixture_scenario(30000)
    short = fixture_scenario(30000, shortfall=True)
    # An actual price infeasibility requires the buyer ceiling to be below the
    # synthetic seller floor. A budget below only the opening offer can still
    # allow a valid negotiated counteroffer.
    budget = NegotiationScenario(buyer=BuyerPrivateInput(requirements=base.buyer.requirements, budget_cents=29000), seller=base.seller)
    restricted = BuyerRequirements(**{**base.buyer.requirements.model_dump(), "allowed_colors": ("navy",)})
    forbidden = NegotiationScenario(buyer=BuyerPrivateInput(requirements=restricted, budget_cents=36000), seller=base.seller)
    depleted_seller = SellerPrivateInput(
        sku="shirts", policy=SellerPolicy(minimum_total_cents=30000), offer_options=base.seller.offer_options,
        stock_batches=(SellerStockBatch(batch_id="friday_navy", color="navy", available_qty=0, deliver_by="2026-11-13"),
                       SellerStockBatch(batch_id="monday_black", color="black", available_qty=18, deliver_by="2026-11-16")),
    )
    competing = NegotiationScenario(buyer=base.buyer, seller=depleted_seller)
    ordinary_requirements = BuyerRequirements(sku="shirts", quantity=10,
        minimum_by_date=({"date": "2026-11-16", "qty": 10},), allowed_colors=("navy",), preferred_color="navy")
    ordinary_offer = OfferTerms(currency="USD", total_cents=12000,
        lines=(OfferLine(color="navy", qty=10, deliver_by="2026-11-16"),))
    ordinary = NegotiationScenario(
        buyer=BuyerPrivateInput(requirements=ordinary_requirements, budget_cents=15000),
        seller=SellerPrivateInput(sku="shirts", policy=SellerPolicy(minimum_total_cents=9000),
            stock_batches=(SellerStockBatch(batch_id="ordinary_navy", color="navy", available_qty=10, deliver_by="2026-11-16"),),
            offer_options=(ordinary_offer,)),
    )
    # Depleted stock models the second buyer's view; the actual concurrency
    # gate is separately exercised against PostgreSQL, not inferred here.
    return (("feasible_split", True, base), ("impossible_deadline", False, short),
            ("budget_shortfall", False, budget), ("forbidden_color", False, forbidden),
            ("competing_buyer_depleted", False, competing), ("ordinary_order", True, ordinary))


class ScriptedBaseline:
    """Simple deterministic comparator with only the current role's inputs."""

    def generate_buyer(self, data):
        latest = next((e for e in reversed(data.shared.events) if e.issued_offer_id), None)
        if latest is None:
            return AskAction(type="ask", topic="delivery_options")
        terms, req = latest.action.terms, data.private.requirements
        if (terms.total_cents > data.private.budget_cents
                or sum(line.qty for line in terms.lines) != req.quantity
                or any(line.color not in req.allowed_colors for line in terms.lines)
                or any(sum(line.qty for line in terms.lines if line.deliver_by <= m.date) < m.qty for m in req.minimum_by_date)):
            return DeclineAction(type="decline", reason_code="terms_unacceptable", offer_id=latest.issued_offer_id)
        return AcceptAction(type="accept", offer_id=latest.issued_offer_id)

    def generate_seller(self, data):
        req, seller = data.shared.requirements, data.private
        if any(sum(batch.available_qty for batch in seller.stock_batches
                   if batch.color in req.allowed_colors and batch.deliver_by <= minimum.date) < minimum.qty
               for minimum in req.minimum_by_date):
            return DeclineAction(type="decline", reason_code="deadline_unavailable")
        latest = next((e for e in reversed(data.shared.events) if e.issued_offer_id), None)
        if latest and latest.actor != "seller" and latest.action.terms.total_cents >= seller.policy.minimum_total_cents:
            return AcceptAction(type="accept", offer_id=latest.issued_offer_id)
        if latest is None and seller.offer_options and seller.offer_options[0].total_cents >= seller.policy.minimum_total_cents:
            return OfferAction(type="offer", terms=seller.offer_options[0])
        return DeclineAction(type="decline", reason_code="terms_unacceptable")


def evaluate(source, scenario, expected_deal, *, limits):
    result = run_negotiation(scenario, source, limits)
    ineligible = sum(bool(assess_offer(event.action.terms, scenario)) for event in result.events
                     if event.action.type in {"offer", "counter"})
    accepted = result.status == "agreed" and not assess_offer(result.agreement, scenario)
    completed = result.status in {"agreed", "no_deal"}
    return {"status": result.status, "reason_code": result.reason_code, "turns": result.turns,
            "ineligible_proposals": ineligible, "invalid_action": result.reason_code == "invalid_action",
            "server_accepted_terms": accepted, "quote_issued": False,
            "matches_expected": (accepted == expected_deal) if completed else None}


def evaluate_with_conversation(source, scenario, expected_deal, *, limits):
    """Record proposed calls and accepted events for isolated synthetic evaluation."""
    attempts = []
    original = negotiation.call_agent_bounded

    def measured(agent, actor, data, timeout_ms):
        turn = {"turn": len(attempts) + 1, "role": actor, "timeout_ms": timeout_ms}
        attempts.append(turn)
        start = time.monotonic()
        try:
            action = original(agent, actor, data, timeout_ms)
            turn.update(proposed_action=action.model_dump(mode="json"), call_status="returned")
            return action
        except ModelCallError as error:
            turn.update(call_status="error", error_code=error.code)
            raise
        except Exception:
            turn.update(call_status="error", error_code="unexpected_error")
            raise
        finally:
            turn["elapsed_ms"] = round((time.monotonic() - start) * 1000)

    negotiation.call_agent_bounded = measured
    try:
        result = negotiation.run_negotiation(scenario, source, limits)
    finally:
        negotiation.call_agent_bounded = original
    events = [event.model_dump(mode="json") for event in result.events]
    for turn in attempts:
        event = next((item for item in events if item["sequence"] == turn["turn"]), None)
        turn["recorded_in_conversation"] = event is not None
        if event is not None:
            turn["issued_offer_id"] = event["issued_offer_id"]
        elif turn["call_status"] == "returned":
            turn["disposition"] = "not_recorded_by_negotiation"
    ineligible = sum(bool(assess_offer(event.action.terms, scenario)) for event in result.events
                     if event.action.type in {"offer", "counter"})
    accepted = result.status == "agreed" and not assess_offer(result.agreement, scenario)
    completed = result.status in {"agreed", "no_deal"}
    return {"status": result.status, "reason_code": result.reason_code, "turns": result.turns,
            "ineligible_proposals": ineligible, "invalid_action": result.reason_code == "invalid_action",
            "server_accepted_terms": accepted, "quote_issued": False,
            "matches_expected": (accepted == expected_deal) if completed else None,
            "conversation": events, "attempts": attempts}


def comparison(candidate, *, candidate_kind, limits=None):
    if candidate_kind not in {"fixture", "live"}:
        raise ValueError("Candidate must be explicitly labeled")
    limits = NegotiationLimits.model_validate(NegotiationLimits() if limits is None else limits)
    baseline = ScriptedBaseline()
    cases = []
    for name, expected, scenario in scenarios():
        if isinstance(candidate, OpenRouterActionClient):
            candidate.trace_case = name
        cases.append({"case": name, "expected_deal": expected,
                      "baseline": evaluate(baseline, scenario, expected, limits=limits),
                      "candidate": evaluate_with_conversation(candidate, scenario, expected, limits=limits)})
    return {"candidate_kind": candidate_kind, "synthetic_policy_and_stock": True,
            "max_turns": limits.max_turns, "quote_issuance_tested": False, "cases": cases}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare six synthetic cases without writing results.")
    parser.add_argument("--candidate", choices=("fixture", "live"), required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--turn-timeout-ms", type=int, default=30000)
    parser.add_argument("--response-trace", type=Path, help="Write sensitive OpenRouter HTTP responses as JSONL (live only).")
    args = parser.parse_args(argv)
    try:
        model = None
        if args.candidate == "live":
            env_file = args.env_file or (Path(__file__).resolve().parents[2] / ".env")
            settings = OpenRouterSettings.from_environment(env_file=env_file)
            model = settings.model
            source = OpenRouterActionClient(settings, response_trace=args.response_trace)
        else:
            if args.response_trace:
                raise ValueError("Response tracing requires live mode")
            source = FixtureAgents()
        limits = NegotiationLimits(max_turns=6, turn_timeout_ms=args.turn_timeout_ms, total_timeout_ms=args.turn_timeout_ms * 6)
        report = comparison(source, candidate_kind=args.candidate, limits=limits)
        report["candidate_model"] = model
        report["max_output_tokens"] = settings.max_output_tokens if args.candidate == "live" else None
        print(json.dumps(report, separators=(",", ":")))
        # An incomplete model/provider run is never a successful evaluation.
        return 0 if all(case["candidate"]["matches_expected"] is True
                        and case["baseline"]["matches_expected"] is True for case in report["cases"]) else 1
    except (ValueError, ModelConfigurationError):
        print("Evaluation configuration is invalid; private details were withheld.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
