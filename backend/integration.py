"""Explicit B4 negotiation service construction; no fixtures or seeded policy."""
import os


def create_negotiation_router():
    from backend.domain.api import NegotiationService, create_router
    from backend.domain.contracts import SellerPolicy, SellerPrivateInput
    from backend.domain.database import DomainDatabase
    from backend.domain.openrouter_client import OpenRouterActionClient
    from backend.domain.openrouter_config import Settings as OpenRouterSettings
    from backend.domain.quotes import QuoteAdapter

    raw_floor = os.getenv("MERCHANT_MINIMUM_TOTAL_CENTS", "")
    if not raw_floor.isascii() or not raw_floor.isdigit() or not 0 < int(raw_floor) <= 9223372036854775807:
        raise RuntimeError("MERCHANT_MINIMUM_TOTAL_CENTS must be explicitly configured as a positive integer")
    floor = int(raw_floor)
    quotes = QuoteAdapter(DomainDatabase.from_environment())
    settings = OpenRouterSettings.from_environment()

    def seller(requirements):
        return SellerPrivateInput(sku=requirements.sku, policy=SellerPolicy(minimum_total_cents=floor), stock_batches=())

    return create_router(NegotiationService(quotes, seller, OpenRouterActionClient(settings), timeout_ms=settings.timeout_ms))
