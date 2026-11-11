"""A1.1 contracts only: no provider calls, persistence, or negotiation engine.

Action inputs are untrusted. PublicEvent metadata must be supplied by trusted
server code; these types do not authenticate actors or validate offer history.
"""

from datetime import date
import re
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints,
    TypeAdapter, computed_field, model_validator,
)


PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]
OfferReference = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
]
Color = Literal["navy", "black"]
Actor = Literal["buyer", "seller"]
AskTopic = Literal["delivery_options", "color_options", "revised_offer"]
DeclineReason = Literal[
    "deadline_unavailable", "budget_infeasible", "color_unavailable", "terms_unacceptable"
]


def _calendar_date(value: object) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("Expected a calendar date in YYYY-MM-DD format")


CalendarDate = Annotated[date, BeforeValidator(_calendar_date)]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always",
        hide_input_in_errors=True,
    )


class DeliveryMinimum(Contract):
    date: CalendarDate
    qty: PositiveInt


class BuyerRequirements(Contract):
    sku: OfferReference
    quantity: PositiveInt
    minimum_by_date: Annotated[tuple[DeliveryMinimum, ...], Field(min_length=1)]
    allowed_colors: Annotated[tuple[Color, ...], Field(min_length=1)]
    preferred_color: Color | None = None

    @model_validator(mode="after")
    def coherent_requirements(self) -> Self:
        if len(set(self.allowed_colors)) != len(self.allowed_colors):
            raise ValueError("Allowed colors must be unique")
        if self.preferred_color is not None and self.preferred_color not in self.allowed_colors:
            raise ValueError("Preferred color must be allowed")
        previous_date = None
        previous_qty = 0
        for minimum in self.minimum_by_date:
            if previous_date is not None and minimum.date <= previous_date:
                raise ValueError("Delivery dates must be unique and increasing")
            if not previous_qty <= minimum.qty <= self.quantity:
                raise ValueError("Cumulative quantities must not decrease or exceed quantity")
            previous_date, previous_qty = minimum.date, minimum.qty
        if previous_qty != self.quantity:
            raise ValueError("Final delivery minimum must cover the full quantity")
        return self


class OfferLine(Contract):
    color: Color
    qty: PositiveInt
    deliver_by: CalendarDate


class OfferTerms(Contract):
    currency: Literal["USD"]
    total_cents: PositiveInt  # Inclusive of delivery.
    lines: Annotated[tuple[OfferLine, ...], Field(min_length=1)]

    def validate_quantity(self, requirements: BuyerRequirements) -> None:
        """Cross-contract quantity check; deliberately not commercial eligibility."""
        if sum(line.qty for line in self.lines) != requirements.quantity:
            raise ValueError("Offer quantity must equal requested quantity")


class AskAction(Contract):
    type: Literal["ask"]
    topic: AskTopic


class OfferAction(Contract):
    type: Literal["offer"]
    terms: OfferTerms


class CounterAction(Contract):
    type: Literal["counter"]
    offer_id: OfferReference
    terms: OfferTerms


class AcceptAction(Contract):
    type: Literal["accept"]
    offer_id: OfferReference


class DeclineAction(Contract):
    type: Literal["decline"]
    reason_code: DeclineReason
    offer_id: OfferReference | None = None


NegotiationAction = Annotated[
    AskAction | OfferAction | CounterAction | AcceptAction | DeclineAction,
    Field(discriminator="type"),
]
ACTION_ADAPTER = TypeAdapter(NegotiationAction)


class BuyerPrivateInput(Contract):
    requirements: BuyerRequirements
    budget_cents: PositiveInt = Field(repr=False)


class SellerStockBatch(Contract):
    batch_id: OfferReference
    color: Color
    available_qty: NonnegativeInt
    deliver_by: CalendarDate


class SellerPolicy(Contract):
    # Required input for this order, never inferred from fixture offer prices.
    minimum_total_cents: PositiveInt = Field(repr=False)


class SellerPrivateInput(Contract):
    sku: OfferReference
    stock_batches: tuple[SellerStockBatch, ...] = Field(repr=False)
    policy: SellerPolicy = Field(repr=False)
    # Optional merchant-supplied starting proposals, never shared until offered.
    offer_options: tuple[OfferTerms, ...] = Field(default=(), repr=False)

    @model_validator(mode="after")
    def unique_batches(self) -> Self:
        ids = [batch.batch_id for batch in self.stock_batches]
        if len(ids) != len(set(ids)):
            raise ValueError("Stock batch IDs must be unique")
        return self


class PublicEvent(Contract):
    """Trusted server envelope; never parse raw model output into this type."""

    event_id: OfferReference
    sequence: PositiveInt
    actor: Actor
    action: NegotiationAction
    issued_offer_id: OfferReference | None = None

    @model_validator(mode="after")
    def offer_identity(self) -> Self:
        proposing = isinstance(self.action, (OfferAction, CounterAction))
        if proposing != (self.issued_offer_id is not None):
            raise ValueError("Only offer/counter events require an issued offer ID")
        return self


class SharedNegotiationContext(Contract):
    requirements: BuyerRequirements
    events: tuple[PublicEvent, ...] = ()

    @model_validator(mode="after")
    def coherent_events(self) -> Self:
        ids: set[str] = set()
        offer_ids: set[str] = set()
        previous = 0
        for event in self.events:
            if event.sequence <= previous or event.event_id in ids:
                raise ValueError("Public events require unique IDs and increasing sequences")
            if event.issued_offer_id is not None:
                if event.issued_offer_id in offer_ids:
                    raise ValueError("Issued offer IDs must be unique")
                offer_ids.add(event.issued_offer_id)
            previous = event.sequence
            ids.add(event.event_id)
        return self


class BuyerAgentInput(Contract):
    private: BuyerPrivateInput = Field(repr=False)
    shared: SharedNegotiationContext

    @model_validator(mode="after")
    def consistent_requirements(self) -> Self:
        if self.private.requirements != self.shared.requirements:
            raise ValueError("Buyer and shared requirements must match")
        return self


class SellerAgentInput(Contract):
    private: SellerPrivateInput = Field(repr=False)
    shared: SharedNegotiationContext

    @model_validator(mode="after")
    def consistent_sku(self) -> Self:
        if self.private.sku != self.shared.requirements.sku:
            raise ValueError("Seller and shared SKU must match")
        return self


class PublicMessage(Contract):
    """Output renderer: accepts an approved event, never arbitrary public text.

    JSON output is the H0 {actor, text} shape. This is an output-only contract,
    not a parser for historical message JSON. Event IDs are not rendered.
    """

    event: PublicEvent = Field(exclude=True, repr=False)

    @computed_field
    @property
    def actor(self) -> Actor:
        return self.event.actor

    @computed_field
    @property
    def text(self) -> str:
        action = self.event.action
        if isinstance(action, AskAction):
            return {
                "delivery_options": "Can you provide delivery options?",
                "color_options": "Can you provide color options?",
                "revised_offer": "Can you provide a revised offer?",
            }[action.topic]
        if isinstance(action, (OfferAction, CounterAction)):
            cents = action.terms.total_cents
            lines = "; ".join(
                f"{line.qty} {line.color} by {line.deliver_by.isoformat()}"
                for line in action.terms.lines
            )
            prefix = "Counteroffer" if isinstance(action, CounterAction) else "Offer"
            return f"{prefix}: USD {cents // 100}.{cents % 100:02d} including delivery; {lines}."
        if isinstance(action, AcceptAction):
            return "The proposed terms are accepted, subject to server validation and stock reservation."
        return {
            "deadline_unavailable": "The delivery requirement cannot be satisfied.",
            "budget_infeasible": "An acceptable price could not be agreed.",
            "color_unavailable": "The requested colors are unavailable.",
            "terms_unacceptable": "The proposed terms are declined.",
        }[action.reason_code]
