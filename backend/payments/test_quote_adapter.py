"""In-memory development substitute only; never use for real checkout.

The signatures match the H0 handoff. A's database-backed adapter replaces this
before integration. State is process-local and is not a stock reservation.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock


class QuoteUnavailable(Exception):
    pass


@dataclass(frozen=True)
class TestQuote:
    id: str
    session: str
    total_cents: int
    currency: str
    expires_at: datetime


class TestQuoteAdapter:
    __test__ = False

    def __init__(self, scenario: str = "valid"):
        if scenario not in {"valid", "expired", "conflict"}:
            raise ValueError("Scenario must be valid, expired, or conflict")
        self.scenario = scenario
        self.quote = TestQuote("test-usd-1", "test-session", 100, "USD", datetime.now(timezone.utc) + timedelta(minutes=-1 if scenario == "expired" else 15))
        self._claim = None
        self._committed = False
        self._lock = Lock()

    def get_quote(self, session: str, quote_id: str) -> TestQuote:
        if session != self.quote.session or quote_id != self.quote.id:
            raise QuoteUnavailable("Quote not found")
        return self.quote

    def claim_for_authorization(self, session: str, quote_id: str, operation_id: str) -> TestQuote:
        if not operation_id:
            raise ValueError("operation_id is required")
        with self._lock:
            quote = self.get_quote(session, quote_id)
            if self._claim == operation_id:
                return quote
            if self._claim is not None or self._committed or self.scenario == "conflict":
                raise QuoteUnavailable("Stock conflict")
            if quote.expires_at <= datetime.now(timezone.utc):
                raise QuoteUnavailable("Quote expired")
            self._claim = operation_id
            return quote

    def commit_allocation(self, operation_id: str) -> None:
        with self._lock:
            if not operation_id or self._claim != operation_id:
                raise QuoteUnavailable("Unknown claim")
            self._committed = True

    def release_claim(self, operation_id: str) -> None:
        with self._lock:
            if operation_id and self._claim == operation_id and not self._committed:
                self._claim = None
