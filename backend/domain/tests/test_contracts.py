"""A1.1 contract and privacy checks; no live providers or database required."""

from datetime import date, datetime, timezone
import json

import pytest
from pydantic import ValidationError

from backend.domain.contracts import (
    ACTION_ADAPTER, AcceptAction, AskAction, BuyerAgentInput, BuyerPrivateInput,
    BuyerRequirements, CounterAction, DeclineAction, DeliveryMinimum, OfferAction,
    OfferLine, OfferTerms, PublicEvent, PublicMessage, SellerAgentInput,
    SellerPolicy, SellerPrivateInput, SellerStockBatch, SharedNegotiationContext,
)
from backend.domain.fixtures import buyer_fixture, monday_offer_fixture, split_offer_fixture


def requirements_payload():
    return buyer_fixture().requirements.model_dump(mode="json")


def offer_payload():
    return split_offer_fixture().model_dump(mode="json")


def action_payload(kind):
    return {
        "ask": {"type": "ask", "topic": "delivery_options"},
        "offer": {"type": "offer", "terms": offer_payload()},
        "counter": {"type": "counter", "offer_id": "old_offer", "terms": offer_payload()},
        "accept": {"type": "accept", "offer_id": "split_offer"},
        "decline": {"type": "decline", "reason_code": "deadline_unavailable"},
    }[kind]


@pytest.mark.parametrize("kind,cls", [
    ("ask", AskAction), ("offer", OfferAction), ("counter", CounterAction),
    ("accept", AcceptAction), ("decline", DeclineAction),
])
def test_every_action_python_and_json(kind, cls):
    payload = action_payload(kind)
    action = ACTION_ADAPTER.validate_python(payload)
    assert isinstance(action, cls)
    assert ACTION_ADAPTER.validate_json(json.dumps(payload)) == action
    assert ACTION_ADAPTER.validate_json(action.model_dump_json()) == action


@pytest.mark.parametrize("kind", ["ask", "offer", "counter", "accept", "decline"])
def test_each_action_missing_required_fields(kind):
    payload = action_payload(kind)
    for field in payload:
        malformed = {key: value for key, value in payload.items() if key != field}
        with pytest.raises(ValidationError):
            ACTION_ADAPTER.validate_python(malformed)


@pytest.mark.parametrize("kind", ["ask", "offer", "counter", "accept", "decline"])
@pytest.mark.parametrize("field", ["actor", "id", "version", "budget_cents", "private_reasoning", "text"])
def test_actions_reject_authority_and_private_fields(kind, field):
    with pytest.raises(ValidationError):
        ACTION_ADAPTER.validate_python({**action_payload(kind), field: "untrusted"})


@pytest.mark.parametrize("payload", [
    {}, {"type": "approve"}, {"type": None}, {"type": 1}, [], "offer", None,
    {"type": "ask", "topic": "buyer_budget"},
    {"type": "decline", "reason_code": "seller_floor_is_30000"},
    {"type": "accept", "offer_id": ""},
    {"type": "accept", "offer_id": "my private budget: 36000"},
    {"type": "accept", "offer_id": "a" * 129},
])
def test_malformed_actions(payload):
    with pytest.raises(ValidationError):
        ACTION_ADAPTER.validate_python(payload)


@pytest.mark.parametrize("value", [-1, 0, "12", 12.0, True, False, None])
@pytest.mark.parametrize("target", ["quantity", "minimum", "line", "total", "budget", "floor"])
def test_positive_integer_fields(value, target):
    with pytest.raises(ValidationError):
        if target == "quantity":
            BuyerRequirements.model_validate({**requirements_payload(), "quantity": value})
        elif target == "minimum":
            DeliveryMinimum(date="2026-11-13", qty=value)
        elif target == "line":
            OfferLine(color="navy", qty=value, deliver_by="2026-11-13")
        elif target == "total":
            OfferTerms.model_validate({**offer_payload(), "total_cents": value})
        elif target == "budget":
            BuyerPrivateInput(requirements=buyer_fixture().requirements, budget_cents=value)
        else:
            SellerPolicy(minimum_total_cents=value)


@pytest.mark.parametrize("value", [-1, "0", 0.0, True, None])
def test_stock_is_strict_and_nonnegative(value):
    with pytest.raises(ValidationError):
        SellerStockBatch(batch_id="batch", color="navy", available_qty=value, deliver_by="2026-11-13")


def test_zero_stock_and_no_supply_are_valid():
    batch = SellerStockBatch(batch_id="batch", color="navy", available_qty=0, deliver_by="2026-11-13")
    assert batch.available_qty == 0
    assert SellerPrivateInput(sku="shirts", stock_batches=(), policy=SellerPolicy(minimum_total_cents=1))


@pytest.mark.parametrize("value", [
    "2026-02-30", "2026-13-01", "2026-11-31", "2026-1-01", "13/11/2026",
    "2026-11-13T00:00:00Z", " 2026-11-13", 1794528000, True, None,
    datetime(2026, 11, 13, tzinfo=timezone.utc),
])
@pytest.mark.parametrize("target", ["minimum", "line", "stock"])
def test_dates_are_calendar_dates_only(value, target):
    with pytest.raises(ValidationError):
        if target == "minimum":
            DeliveryMinimum(date=value, qty=12)
        elif target == "line":
            OfferLine(color="navy", qty=12, deliver_by=value)
        else:
            SellerStockBatch(batch_id="batch", color="navy", available_qty=12, deliver_by=value)


def test_dates_use_date_objects_and_iso_json():
    for value in (date(2026, 11, 13), "2026-11-13"):
        minimum = DeliveryMinimum(date=value, qty=12)
        assert type(minimum.date) is date
        assert json.loads(minimum.model_dump_json())["date"] == "2026-11-13"
    assert DeliveryMinimum(date="2028-02-29", qty=1).date == date(2028, 2, 29)


@pytest.mark.parametrize("minimums", [
    [],
    [{"date": "2026-11-13", "qty": 12}, {"date": "2026-11-13", "qty": 30}],
    [{"date": "2026-11-16", "qty": 12}, {"date": "2026-11-13", "qty": 30}],
    [{"date": "2026-11-13", "qty": 20}, {"date": "2026-11-16", "qty": 12}],
    [{"date": "2026-11-13", "qty": 31}, {"date": "2026-11-16", "qty": 30}],
    [{"date": "2026-11-16", "qty": 18}],
])
def test_invalid_cumulative_deadlines(minimums):
    with pytest.raises(ValidationError):
        BuyerRequirements.model_validate({**requirements_payload(), "minimum_by_date": minimums})


def test_single_deadline_and_equal_cumulative_minimums():
    payload = requirements_payload()
    payload["minimum_by_date"] = [{"date": "2026-11-13", "qty": 30}]
    assert BuyerRequirements.model_validate(payload)
    payload["minimum_by_date"].append({"date": "2026-11-16", "qty": 30})
    assert BuyerRequirements.model_validate(payload)


@pytest.mark.parametrize("patch", [
    {"allowed_colors": []}, {"allowed_colors": ["navy", "navy"]},
    {"allowed_colors": ["red"]}, {"preferred_color": "red"},
    {"allowed_colors": ["black"], "preferred_color": "navy"},
    {"quantity": 30, "unexpected": 1}, {"sku": ""},
])
def test_buyer_colors_and_unknown_fields(patch):
    with pytest.raises(ValidationError):
        BuyerRequirements.model_validate({**requirements_payload(), **patch})


@pytest.mark.parametrize("patch", [{"color": "red"}, {"color": None}, {"budget_cents": 36000}])
def test_offer_line_rejects_unsupported_fields_and_colors(patch):
    with pytest.raises(ValidationError):
        OfferLine.model_validate({"color": "navy", "qty": 30, "deliver_by": "2026-11-16", **patch})


@pytest.mark.parametrize("patch", [{"lines": []}, {"currency": "EUR"}, {"currency": "usd"}, {"floor": 1}])
def test_invalid_offer_terms(patch):
    with pytest.raises(ValidationError):
        OfferTerms.model_validate({**offer_payload(), **patch})


def test_quantity_cross_check_and_commercial_separation():
    buyer = buyer_fixture()
    split = split_offer_fixture()
    assert split.validate_quantity(buyer.requirements) is None
    short = {**offer_payload(), "lines": [{"color": "navy", "qty": 29, "deliver_by": "2026-11-13"}]}
    with pytest.raises(ValueError, match="quantity"):
        OfferTerms.model_validate(short).validate_quantity(buyer.requirements)
    # Structurally valid, full-quantity proposals remain parseable even if infeasible.
    infeasible = OfferTerms.model_validate({
        **offer_payload(), "total_cents": 36001,
        "lines": [{"color": "black", "qty": 30, "deliver_by": "2026-11-17"}],
    })
    assert infeasible.validate_quantity(buyer.requirements) is None
    assert infeasible.total_cents > buyer.budget_cents
    # A supported but buyer-forbidden color is also a commercial constraint.
    navy_only = BuyerRequirements.model_validate({**requirements_payload(), "allowed_colors": ["navy"]})
    assert split.validate_quantity(navy_only) is None


@pytest.mark.parametrize("qty", [29, 31])
def test_under_and_over_quantity(qty):
    terms = OfferTerms.model_validate({**offer_payload(), "lines": [
        {"color": "navy", "qty": qty, "deliver_by": "2026-11-13"},
    ]})
    with pytest.raises(ValueError, match="quantity"):
        terms.validate_quantity(buyer_fixture().requirements)


@pytest.mark.parametrize("value", ["35400", 35400.0, True, False, 0, -1])
def test_action_json_also_enforces_strict_integer_cents(value):
    payload = action_payload("offer")
    payload["terms"]["total_cents"] = value
    with pytest.raises(ValidationError):
        ACTION_ADAPTER.validate_json(json.dumps(payload))


@pytest.mark.parametrize("value", ["12", 12.0, True, False, 0, -1])
def test_action_json_also_enforces_strict_integer_quantities(value):
    payload = action_payload("offer")
    payload["terms"]["lines"][0]["qty"] = value
    with pytest.raises(ValidationError):
        ACTION_ADAPTER.validate_json(json.dumps(payload))


def seller_input():
    # Synthetic boundary-test value only, not a fixture merchant floor.
    return SellerPrivateInput(
        sku="shirts", stock_batches=(SellerStockBatch(
            batch_id="private_batch", color="navy", available_qty=77, deliver_by="2026-11-13",
        ),), policy=SellerPolicy(minimum_total_cents=12345),
    )


def event(kind="offer", **updates):
    return PublicEvent.model_validate({
        "event_id": "event_1", "sequence": 1, "actor": "seller",
        "action": action_payload(kind),
        "issued_offer_id": "offer_1" if kind in {"offer", "counter"} else None,
        **updates,
    })


def test_role_separation_and_serialized_boundaries():
    shared = SharedNegotiationContext(requirements=buyer_fixture().requirements, events=(event(),))
    buyer = BuyerAgentInput(private=buyer_fixture(), shared=shared)
    seller = SellerAgentInput(private=seller_input(), shared=shared)
    assert "budget_cents" in buyer.model_dump_json()
    assert "minimum_total_cents" not in buyer.model_dump_json()
    assert "private_batch" not in buyer.model_dump_json()
    assert "budget_cents" not in seller.model_dump_json()
    assert "minimum_total_cents" in seller.model_dump_json()
    for forbidden in ("budget_cents", "minimum_total_cents", "stock_batches", "private_batch"):
        assert forbidden not in shared.model_dump_json()
    with pytest.raises(ValidationError):
        BuyerAgentInput(private=seller_input(), shared=shared)
    with pytest.raises(ValidationError):
        SellerAgentInput(private=buyer_fixture(), shared=shared)
    for forbidden in ("budget_cents", "policy", "private", "stock_batches", "raw_response"):
        with pytest.raises(ValidationError):
            SharedNegotiationContext.model_validate({**shared.model_dump(), forbidden: {}})


def test_input_consistency_and_duplicate_stock():
    shared = SharedNegotiationContext(requirements=buyer_fixture().requirements)
    different = BuyerPrivateInput(requirements=BuyerRequirements.model_validate({
        **requirements_payload(), "sku": "other",
    }), budget_cents=36000)
    with pytest.raises(ValidationError):
        BuyerAgentInput(private=different, shared=shared)
    with pytest.raises(ValidationError):
        SellerAgentInput(private=SellerPrivateInput(
            sku="other", stock_batches=(), policy=SellerPolicy(minimum_total_cents=1),
        ), shared=shared)
    batch = seller_input().stock_batches[0]
    with pytest.raises(ValidationError):
        SellerPrivateInput(sku="shirts", stock_batches=(batch, batch), policy=seller_input().policy)


@pytest.mark.parametrize("kind", ["ask", "offer", "counter", "accept", "decline"])
def test_public_messages_only_render_approved_data(kind):
    message = PublicMessage(event=event(kind))
    output = json.loads(message.model_dump_json())
    assert set(output) == {"actor", "text"}
    assert output["actor"] == "seller"
    assert output["text"]
    for forbidden in ("budget_cents", "minimum_total_cents", "private_batch", "offer_1", "old_offer"):
        assert forbidden not in message.model_dump_json()
    if kind in {"offer", "counter"}:
        assert "354.00" in output["text"]
        assert "12 navy by 2026-11-13" in output["text"]
    with pytest.raises(ValidationError):
        PublicMessage(event=event(kind), text="My budget is 36000")
    with pytest.raises(ValidationError):
        PublicMessage(actor="buyer", text="My budget is 36000")


@pytest.mark.parametrize("topic", ["delivery_options", "color_options", "revised_offer"])
def test_all_ask_templates(topic):
    assert PublicMessage(event=event("ask", action={"type": "ask", "topic": topic})).text.endswith("?")


@pytest.mark.parametrize("reason", ["deadline_unavailable", "budget_infeasible", "color_unavailable", "terms_unacceptable"])
def test_all_decline_templates(reason):
    assert PublicMessage(event=event("decline", action={"type": "decline", "reason_code": reason})).text


@pytest.mark.parametrize("patch", [
    {"sequence": 0}, {"sequence": True}, {"actor": "system"},
    {"issued_offer_id": None}, {"raw_response": "secret"}, {"private": {}},
])
def test_public_event_rejects_invalid_metadata(patch):
    with pytest.raises(ValidationError):
        event(**patch)


def test_public_event_and_context_consistency():
    with pytest.raises(ValidationError):
        event("accept", issued_offer_id="cannot_issue")
    first = event()
    for second in (
        event(event_id="event_2"),
        event(sequence=2),
        event(event_id="event_2", sequence=2),
    ):
        with pytest.raises(ValidationError):
            SharedNegotiationContext(requirements=buyer_fixture().requirements, events=(first, second))
    second = event(event_id="event_2", sequence=2, issued_offer_id="offer_2")
    assert SharedNegotiationContext(requirements=buyer_fixture().requirements, events=(first, second))


def test_fixture_facts_and_json_roundtrip():
    buyer, split, monday = buyer_fixture(), split_offer_fixture(), monday_offer_fixture()
    assert buyer.budget_cents == 36000
    assert [(x.date, x.qty) for x in buyer.requirements.minimum_by_date] == [
        (date(2026, 11, 13), 12), (date(2026, 11, 16), 30),
    ]
    assert split.total_cents == 35400
    assert sum(line.qty for line in split.lines if line.deliver_by <= date(2026, 11, 13)) == 12
    assert monday.total_cents == 33000 and monday.quantity == 30
    assert monday.deliver_by > buyer.requirements.minimum_by_date[0].date
    assert "color" not in monday.model_dump_json()
    assert "minimum_total_cents" not in monday.model_dump_json()
    assert BuyerPrivateInput.model_validate_json(buyer.model_dump_json()) == buyer
    with pytest.raises(ValidationError):
        OfferTerms.model_validate(monday.model_dump())


def test_immutable_contracts_and_json_schema():
    requirements = buyer_fixture().requirements
    with pytest.raises(ValidationError):
        requirements.quantity = 1
    assert isinstance(requirements.minimum_by_date, tuple)
    schema = ACTION_ADAPTER.json_schema()
    assert schema["discriminator"]["propertyName"] == "type"
    assert len(schema["oneOf"]) == 5
    assert set(PublicMessage.model_json_schema(mode="serialization")["properties"]) == {"actor", "text"}


@pytest.mark.parametrize("cls,payload", [
    (DeliveryMinimum, {"date": "2026-11-13", "qty": 12}),
    (BuyerPrivateInput, buyer_fixture().model_dump()),
    (SellerStockBatch, seller_input().stock_batches[0].model_dump()),
    (SellerPolicy, {"minimum_total_cents": 12345}),
    (SellerPrivateInput, seller_input().model_dump()),
    (SharedNegotiationContext, {"requirements": requirements_payload()}),
    (BuyerAgentInput, {"private": buyer_fixture(), "shared": {"requirements": requirements_payload()}}),
    (SellerAgentInput, {"private": seller_input(), "shared": {"requirements": requirements_payload()}}),
])
def test_other_contracts_reject_unknown_fields_and_missing_required_fields(cls, payload):
    with pytest.raises(ValidationError):
        cls.model_validate({**payload, "raw_response": "private"})
    for field, definition in cls.model_fields.items():
        if definition.is_required():
            with pytest.raises(ValidationError):
                cls.model_validate({key: value for key, value in payload.items() if key != field})


def test_private_validation_error_string_hides_rejected_inputs():
    with pytest.raises(ValidationError) as caught:
        SellerPolicy(minimum_total_cents="private_marker_12345")
    assert "private_marker_12345" not in str(caught.value)
    # Structured error dictionaries may still contain inputs: never publish/log them.
    assert "private_marker_12345" not in str(caught.value.errors(include_input=False))


def test_offer_public_rendering_is_exact_integer_cents():
    payload = action_payload("offer")
    payload["terms"]["total_cents"] = 35401
    assert "USD 354.01" in PublicMessage(event=event(action=payload)).text
