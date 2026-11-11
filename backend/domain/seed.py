"""Explicit synthetic inventory seed; never reset or overwrite reservations."""

import argparse
from pathlib import Path
import sys

from .contracts import SellerStockBatch
from .database import DomainDatabase, DomainError
from .fixtures import buyer_fixture


def seed_fixture(database: DomainDatabase, scenario: str) -> int:
    """Atomically insert missing fixture batches; reject mismatched existing rows.

    Stock quantities and dates are synthetic development inputs. No seller
    policy is written by this function. Existing reservation and allocation
    counters are never updated.
    """
    if not isinstance(scenario, str) or scenario not in {"split", "shortfall"}:
        raise DomainError("invalid_input")
    batches = sorted((
        SellerStockBatch(batch_id="friday_navy", color="navy", available_qty=8 if scenario == "shortfall" else 12, deliver_by="2026-11-13"),
        SellerStockBatch(batch_id="monday_black", color="black", available_qty=18, deliver_by="2026-11-16"),
    ), key=lambda batch: batch.batch_id)
    sku = buyer_fixture().requirements.sku
    inserted = 0
    with database.transaction() as connection:
        for batch in batches:
            # The same lock namespace as QuoteAdapter.add_stock_batch.
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("domain-stock:" + batch.batch_id,))
        existing = {}
        for batch in batches:
            row = connection.execute("SELECT * FROM domain_stock_batches WHERE id = %s FOR UPDATE", (batch.batch_id,)).fetchone()
            expected = (sku, batch.color, batch.deliver_by, batch.available_qty)
            if row and (row["sku"], row["color"], row["arrives_on"], row["total_qty"]) != expected:
                raise DomainError("stock_conflict")
            existing[batch.batch_id] = bool(row)
        for batch in batches:
            if not existing[batch.batch_id]:
                connection.execute("INSERT INTO domain_stock_batches (id, sku, color, arrives_on, total_qty) VALUES (%s, %s, %s, %s, %s)",
                                   (batch.batch_id, sku, batch.color, batch.deliver_by, batch.available_qty))
                inserted += 1
    return inserted


def main(argv=None):
    parser = argparse.ArgumentParser(description="Seed synthetic domain stock into an explicitly configured database.")
    parser.add_argument("--scenario", choices=("split", "shortfall"), required=True)
    parser.add_argument("--acknowledge-synthetic", action="store_true", required=True,
                        help="Confirm this is test stock, not merchant-approved inventory.")
    parser.add_argument("--env-file", type=Path, help="Optional explicit environment file; process settings take precedence.")
    args = parser.parse_args(argv)
    try:
        count = seed_fixture(DomainDatabase.from_environment(env_file=args.env_file), args.scenario)
        print(f"Synthetic {args.scenario} stock: {count} batch(es) inserted; existing counters preserved.")
        return 0
    except DomainError as error:
        print(f"Synthetic seed failed [{error.code}]: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
