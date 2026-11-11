"""Approved business fixtures, not scripted model outcomes or live inventory."""

from datetime import date
from .contracts import (
    BuyerPrivateInput, BuyerRequirements, Contract, DeliveryMinimum,
    OfferLine, OfferTerms, PositiveInt, CalendarDate,
)


def buyer_fixture() -> BuyerPrivateInput:
    return BuyerPrivateInput(
        requirements=BuyerRequirements(
            sku="shirts", quantity=30,
            minimum_by_date=(
                DeliveryMinimum(date=date(2026, 11, 13), qty=12),
                DeliveryMinimum(date=date(2026, 11, 16), qty=30),
            ),
            allowed_colors=("navy", "black"), preferred_color="navy",
        ),
        budget_cents=36000,
    )


def split_offer_fixture() -> OfferTerms:
    return OfferTerms(
        currency="USD", total_cents=35400,
        lines=(
            OfferLine(color="navy", qty=12, deliver_by=date(2026, 11, 13)),
            OfferLine(color="black", qty=18, deliver_by=date(2026, 11, 16)),
        ),
    )


class UnallocatedOfferFixture(Contract):
    """Fixture facts only: cannot be used as actionable OfferTerms without colors."""

    quantity: PositiveInt
    total_cents: PositiveInt
    deliver_by: CalendarDate


def monday_offer_fixture() -> UnallocatedOfferFixture:
    return UnallocatedOfferFixture(
        quantity=30, total_cents=33000, deliver_by=date(2026, 11, 16)
    )
