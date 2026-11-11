"""State-machine tests use explicitly injected deterministic agents, never AI."""

from pydantic import ValidationError
import pytest

from backend.domain import negotiation as module
from backend.domain.contracts import (
    AcceptAction, AskAction, CounterAction, DeclineAction, OfferAction, OfferTerms,
    SellerPrivateInput, SellerStockBatch,
)
from backend.domain.fixtures import split_offer_fixture
from backend.domain.model_client import ModelCallError
from backend.domain.negotiation import (
    NegotiationLimits, NegotiationResult, NegotiationScenario, assess_offer,
    run_negotiation,
)
from backend.domain.negotiation_fixtures import FixtureAgents, fixture_scenario


@pytest.fixture(autouse=True)
def direct_calls(monkeypatch):
    # Only pure state-machine unit tests bypass process creation. The actual
    # bounded process and terminal path have separate integration tests.
    monkeypatch.setattr(module, "call_agent_bounded", lambda source, actor, data, timeout: getattr(source, f"generate_{actor}")(data))


class ScriptedAgents:
    def __init__(self, actions):
        self.actions = actions
        self.calls = []

    def _generate(self, actor, data):
        self.calls.append((actor, data))
        action = self.actions[len(data.shared.events)]
        if isinstance(action, Exception):
            raise action
        return action(data) if callable(action) else action

    def generate_buyer(self, data):
        return self._generate("buyer", data)

    def generate_seller(self, data):
        return self._generate("seller", data)


def ask():
    return AskAction(type="ask", topic="delivery_options")


def offer(terms=None):
    return OfferAction(type="offer", terms=terms or split_offer_fixture())


def active(data):
    return next(e for e in reversed(data.shared.events) if e.issued_offer_id is not None)


def accept(data):
    return AcceptAction(type="accept", offer_id=active(data).issued_offer_id)


def counter(total):
    def action(data):
        terms = OfferTerms.model_validate({**split_offer_fixture().model_dump(), "total_cents": total})
        return CounterAction(type="counter", offer_id=active(data).issued_offer_id, terms=terms)
    return action


def changed(scenario, *, buyer=None, seller=None):
    return NegotiationScenario(buyer=buyer or scenario.buyer, seller=seller or scenario.seller)


def test_split_offer_eligible_and_stock_unchanged():
    scenario = fixture_scenario(30000)  # Synthetic policy for tests only.
    before = scenario.model_dump_json()
    assert assess_offer(split_offer_fixture(), scenario) == ()
    result = run_negotiation(scenario, FixtureAgents())
    assert result.status == "agreed" and result.turns == 3
    assert result.agreement == split_offer_fixture() and result.quote is None
    assert scenario.model_dump_json() == before
    assert [event.actor for event in result.events] == ["buyer", "seller", "buyer"]
    assert "not reserved" in result.reason


def test_ask_offer_counter_counter_accept_freezes_final_terms():
    source = ScriptedAgents([ask(), offer(), counter(35000), counter(35200), accept])
    result = run_negotiation(fixture_scenario(30000), source)
    assert result.status == "agreed" and result.turns == 5
    assert result.agreement.total_cents == 35200
    assert result.events[1].action.terms.total_cents == 35400
    assert result.events[2].action.terms.total_cents == 35000
    assert len({e.issued_offer_id for e in result.events if e.issued_offer_id}) == 3


def test_seller_can_accept_buyer_proposal():
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([offer(), accept]))
    assert result.status == "agreed" and result.turns == 2


def test_ask_does_not_invalidate_active_offer():
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([ask(), offer(), ask(), ask(), accept]))
    assert result.status == "agreed" and result.turns == 5


def test_requested_revision_allows_seller_to_revise_own_offer():
    revised = AskAction(type="ask", topic="revised_offer")
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([ask(), offer(), revised, counter(35300), accept]))
    assert result.status == "agreed" and result.agreement.total_cents == 35300
    assert result.events[1].issued_offer_id != result.events[3].issued_offer_id


def test_self_revision_without_revision_request_is_rejected():
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([ask(), offer(), ask(), counter(35300)]))
    assert result.status == "error" and result.reason_code == "invalid_action"


def test_fixture_seller_answers_revision_request_without_self_accepting():
    revised = AskAction(type="ask", topic="revised_offer")
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([
        ask(), offer(), revised, FixtureAgents().generate_seller, accept,
    ]))
    assert result.status == "agreed" and result.events[3].action.type == "counter"


@pytest.mark.parametrize("actions", [
    [AcceptAction(type="accept", offer_id="unknown")],
    [CounterAction(type="counter", offer_id="unknown", terms=split_offer_fixture())],
    [DeclineAction(type="decline", reason_code="terms_unacceptable", offer_id="unknown")],
    [ask(), offer(), AcceptAction(type="accept", offer_id="foreign_offer")],
    [offer(), ask(), accept],  # Cannot accept one's own offer.
    [ask(), offer(), offer()],  # Must use counter after an initial proposal.
])
def test_invalid_references_and_action_order_never_agree(actions):
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents(actions))
    assert result.status == "error" and result.reason_code == "invalid_action"
    assert result.agreement is None and result.quote is None
    assert len(result.events) == result.turns - 1


def test_stale_offer_acceptance_rejected():
    def stale(data):
        return AcceptAction(type="accept", offer_id=data.shared.events[1].issued_offer_id)
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([ask(), offer(), counter(35000), stale]))
    assert result.reason_code == "invalid_action" and result.agreement is None


@pytest.mark.parametrize("targeted", [False, True])
def test_decline_stops_without_a_quote(targeted):
    def decline(data):
        return DeclineAction(type="decline", reason_code="terms_unacceptable", offer_id=active(data).issued_offer_id if targeted else None)
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([ask(), offer(), decline]))
    assert result.status == "no_deal" and result.reason_code == "declined"
    assert result.turns == 3 and result.agreement is None


def test_friday_shortfall_explains_four_shirts_without_batch_ids():
    scenario = fixture_scenario(30000, shortfall=True)
    result = run_negotiation(scenario, FixtureAgents())
    assert result.status == "no_deal" and result.agreement is None and result.quote is None
    friday = next(issue for issue in result.issues if issue.deliver_by.isoformat() == "2026-11-13")
    assert friday.shortfall_qty == 4 and "4 more shirts" in friday.message
    serialized = result.model_dump_json()
    for private_key in ("budget_cents", "minimum_total_cents", "stock_batches", "offer_options", "friday_navy", "monday_black"):
        assert private_key not in serialized


@pytest.mark.parametrize("price", [29999, 36001])
def test_private_price_failures_are_generic_and_not_accepted(price):
    terms = OfferTerms.model_validate({**split_offer_fixture().model_dump(), "total_cents": price})
    assert terms.total_cents == price  # Proposal remains structurally valid.
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([ask(), offer(terms), accept]))
    assert result.status == "no_deal" and result.reason_code == "ineligible_offer"
    assert [issue.code for issue in result.issues] == ["price_unacceptable"]
    assert len(result.events) == 2  # No false public acceptance event.
    assert "minimum_total_cents" not in result.model_dump_json()


def test_price_boundaries_are_inclusive():
    for price in (30000, 36000):
        terms = OfferTerms.model_validate({**split_offer_fixture().model_dump(), "total_cents": price})
        assert not assess_offer(terms, fixture_scenario(30000))


def test_monday_only_misses_friday_even_if_stock_is_available():
    scenario = fixture_scenario(30000)
    # This synthetic test explicitly assigns black. The actual Monday fixture
    # remains unallocated and no production color assumption is made.
    seller = SellerPrivateInput(sku="shirts", stock_batches=(SellerStockBatch(
        batch_id="synthetic_black_monday", color="black", available_qty=30, deliver_by="2026-11-16",
    ),), policy=scenario.seller.policy)
    scenario = changed(scenario, seller=seller)
    monday = OfferTerms(currency="USD", total_cents=33000, lines=({"color": "black", "qty": 30, "deliver_by": "2026-11-16"},))
    issues = assess_offer(monday, scenario)
    assert [issue.code for issue in issues] == ["deadline_unavailable"]
    assert issues[0].shortfall_qty == 12
    result = run_negotiation(scenario, ScriptedAgents([ask(), offer(monday), accept]))
    assert result.status == "no_deal" and result.agreement is None


@pytest.mark.parametrize("quantity", [29, 31])
def test_offer_quantity_is_enforced_at_acceptance(quantity):
    terms = OfferTerms(currency="USD", total_cents=35400, lines=({"color": "navy", "qty": quantity, "deliver_by": "2026-11-13"},))
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([ask(), offer(terms), accept]))
    assert result.status == "no_deal"
    assert "quantity_mismatch" in [issue.code for issue in result.issues]


def test_supported_but_forbidden_color_and_preference_is_not_mandatory():
    scenario = fixture_scenario(30000)
    requirements = scenario.buyer.requirements.model_copy(update={"allowed_colors": ("navy",)})
    buyer = scenario.buyer.model_copy(update={"requirements": requirements})
    assert "color_unavailable" in [x.code for x in assess_offer(split_offer_fixture(), changed(scenario, buyer=buyer))]
    # Navy is preferred, but an all-black Friday offer is eligible when backed.
    seller = SellerPrivateInput(sku="shirts", stock_batches=(SellerStockBatch(
        batch_id="synthetic_black_friday", color="black", available_qty=30, deliver_by="2026-11-13",
    ),), policy=scenario.seller.policy)
    all_black = OfferTerms(currency="USD", total_cents=35400, lines=({"color": "black", "qty": 30, "deliver_by": "2026-11-13"},))
    assert not assess_offer(all_black, changed(scenario, seller=seller))


def test_repeated_lines_cannot_reuse_the_same_stock():
    scenario = fixture_scenario(30000)
    terms = OfferTerms(currency="USD", total_cents=35400, lines=(
        {"color": "navy", "qty": 12, "deliver_by": "2026-11-13"},
        {"color": "navy", "qty": 18, "deliver_by": "2026-11-16"},
    ))
    assert "stock_unavailable" in [x.code for x in assess_offer(terms, scenario)]
    # Monday navy stock cannot satisfy the Friday line.
    seller = SellerPrivateInput(sku="shirts", stock_batches=(SellerStockBatch(
        batch_id="late_navy", color="navy", available_qty=30, deliver_by="2026-11-16",
    ),), policy=scenario.seller.policy)
    assert "stock_unavailable" in [x.code for x in assess_offer(terms, changed(scenario, seller=seller))]


def test_split_across_multiple_earlier_stock_batches():
    scenario = fixture_scenario(30000)
    seller = SellerPrivateInput(sku="shirts", policy=scenario.seller.policy, stock_batches=(
        SellerStockBatch(batch_id="n1", color="navy", available_qty=5, deliver_by="2026-11-12"),
        SellerStockBatch(batch_id="n2", color="navy", available_qty=7, deliver_by="2026-11-13"),
        SellerStockBatch(batch_id="b1", color="black", available_qty=18, deliver_by="2026-11-16"),
    ))
    assert not assess_offer(split_offer_fixture(), changed(scenario, seller=seller))


def test_six_total_turns_and_new_runs_start_fresh():
    source = ScriptedAgents([ask()] * 6)
    for _ in range(2):
        result = run_negotiation(fixture_scenario(30000), source)
        assert result.turns == 6 and result.reason_code == "turn_limit"
        assert len(result.events) == 6 and result.agreement is None


@pytest.mark.parametrize("patch", [{"max_turns": 0}, {"max_turns": 7}, {"max_turns": True}, {"max_turns": "6"}, {"turn_timeout_ms": 99}, {"turn_timeout_ms": 60001}, {"total_timeout_ms": 0}, {"total_timeout_ms": 360001}, {"unexpected": 1}])
def test_invalid_limits(patch):
    with pytest.raises(ValidationError):
        NegotiationLimits(**patch)


def test_falsy_invalid_limits_do_not_silently_use_defaults():
    with pytest.raises(ValidationError):
        run_negotiation(fixture_scenario(30000), FixtureAgents(), limits=0)


@pytest.mark.parametrize("bad", [None, {}, {"type": "approve"}, {"type": "accept"}, {"type": "ask", "topic": "delivery_options", "actor": "seller"}])
def test_malformed_actions_cannot_produce_agreement_or_quote(bad):
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([bad]))
    assert result.reason_code == "invalid_action" and result.events == ()
    assert result.agreement is None and result.quote is None


@pytest.mark.parametrize("code,status,reason", [
    ("timeout", "retryable_error", "timeout"), ("rate_limited", "retryable_error", "model_error"),
    ("provider_unavailable", "retryable_error", "model_error"), ("network_error", "retryable_error", "model_error"),
    ("credentials_rejected", "error", "model_error"), ("invalid_response", "error", "invalid_action"),
])
def test_model_failures_never_fall_back_to_fixture_success(code, status, reason):
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([ModelCallError(code)]))
    assert (result.status, result.reason_code) == (status, reason)
    assert not result.events and result.agreement is None


def test_unexpected_exception_is_sanitized():
    result = run_negotiation(fixture_scenario(30000), ScriptedAgents([RuntimeError("private_exception_marker")]))
    assert result.status == "error" and "private_exception_marker" not in result.model_dump_json()


def test_private_role_inputs_are_never_shared_or_returned():
    scenario = fixture_scenario(30000)
    source = ScriptedAgents([ask(), offer(), accept])
    result = run_negotiation(scenario, source)
    for actor, data in source.calls:
        serialized = data.model_dump_json()
        assert "minimum_total_cents" not in serialized if actor == "buyer" else "budget_cents" not in serialized
        assert "offer_options" not in data.shared.model_dump_json()
        assert "stock_batches" not in data.shared.model_dump_json()
    for private in ("budget_cents", "minimum_total_cents", "offer_options", "stock_batches", "friday_navy", "monday_black"):
        assert private not in result.model_dump_json()


def test_private_merchant_options_are_published_only_by_sellers_action():
    source = ScriptedAgents([ask(), offer(), accept])
    run_negotiation(fixture_scenario(30000), source)
    first_buyer = source.calls[0][1]
    seller = source.calls[1][1]
    next_buyer = source.calls[2][1]
    assert "offer_options" not in first_buyer.model_dump_json()
    assert first_buyer.shared.events == ()
    assert seller.private.offer_options == (split_offer_fixture(),)
    assert not any(event.issued_offer_id for event in seller.shared.events)
    assert next_buyer.shared.events[1].action.terms == split_offer_fixture()


def test_late_action_is_discarded(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    def slow(source, actor, data, timeout):
        clock[0] += .2
        return ask()
    monkeypatch.setattr(module, "call_agent_bounded", slow)
    result = run_negotiation(fixture_scenario(30000), FixtureAgents(), NegotiationLimits(turn_timeout_ms=100))
    assert result.reason_code == "timeout" and result.events == ()


def test_remaining_total_budget_bounds_later_calls(monkeypatch):
    clock, budgets = [0.0], []
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    def call(source, actor, data, timeout):
        budgets.append(timeout)
        clock[0] += .06
        return ask()
    monkeypatch.setattr(module, "call_agent_bounded", call)
    result = run_negotiation(fixture_scenario(30000), FixtureAgents(), NegotiationLimits(turn_timeout_ms=100, total_timeout_ms=100))
    assert result.reason_code == "timeout" and len(result.events) == 1
    assert budgets[0] == 100 and 39 <= budgets[1] <= 40


def test_total_deadline_before_first_call(monkeypatch):
    clock = iter([0.0, 1.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    result = run_negotiation(fixture_scenario(30000), FixtureAgents(), NegotiationLimits(total_timeout_ms=100))
    assert result.turns == 0 and result.reason_code == "timeout"


def test_seller_floor_required_and_sku_must_match():
    with pytest.raises(TypeError):
        fixture_scenario()
    scenario = fixture_scenario(30000)
    payload = scenario.model_dump()
    del payload["seller"]["policy"]["minimum_total_cents"]
    with pytest.raises(ValidationError):
        NegotiationScenario.model_validate(payload)
    with pytest.raises(ValidationError):
        changed(scenario, seller=scenario.seller.model_copy(update={"sku": "other"}))


def test_result_rejects_false_success_and_quote():
    for patch in (
        {"status": "agreed", "reason_code": "agreed", "turns": 0},
        {"status": "no_deal", "reason_code": "declined", "turns": 0, "agreement": split_offer_fixture()},
        {"status": "no_deal", "reason_code": "declined", "turns": 0, "quote": {"id": "fake"}},
    ):
        with pytest.raises(ValidationError):
            NegotiationResult(**patch)
