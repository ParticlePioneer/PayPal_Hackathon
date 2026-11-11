"""Run a local, simulated quote claim: python -m backend.payments.quote_harness."""
import argparse
from backend.payments.test_quote_adapter import QuoteUnavailable, TestQuoteAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Local-only USD 1 quote adapter harness; no payment is made.")
    parser.add_argument("--scenario", choices=("valid", "expired", "conflict"), default="valid")
    args = parser.parse_args()
    adapter = TestQuoteAdapter(args.scenario)
    try:
        quote = adapter.claim_for_authorization("test-session", "test-usd-1", "test-operation")
    except QuoteUnavailable as exc:
        print(f"Claim rejected: {exc}")
        return 0
    print(f"Claimed {quote.id}: {quote.currency} {quote.total_cents} cents; expires {quote.expires_at.isoformat()}. Simulated only.")
    adapter.release_claim("test-operation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
