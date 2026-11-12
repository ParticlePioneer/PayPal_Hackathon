"""Add explicitly simulated B5 stock without changing existing batches."""
import argparse
import sys

from .database import DomainDatabase, DomainError


BATCHES = (
    ("b5_friday_navy", "shirts", "navy", "2026-11-13", 12),
    ("b5_monday_black", "shirts", "black", "2026-11-16", 18),
)


def seed_b5(database):
    inserted = 0
    with database.transaction() as connection:
        for batch_id, *_ in BATCHES:
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("domain-stock:" + batch_id,))
        for batch_id, sku, color, arrives_on, total in BATCHES:
            row = connection.execute("SELECT * FROM domain_stock_batches WHERE id = %s FOR UPDATE", (batch_id,)).fetchone()
            if row:
                if (row["sku"], row["color"], row["arrives_on"].isoformat(), row["total_qty"]) != (sku, color, arrives_on, total):
                    raise DomainError("stock_conflict")
            else:
                connection.execute("INSERT INTO domain_stock_batches (id, sku, color, arrives_on, total_qty) VALUES (%s, %s, %s, %s, %s)",
                                   (batch_id, sku, color, arrives_on, total))
                inserted += 1
        rows = connection.execute("SELECT id, sku, color, arrives_on, total_qty, reserved_qty, allocated_qty FROM domain_stock_batches WHERE id = ANY(%s) ORDER BY id", ([b[0] for b in BATCHES],)).fetchall()
    return inserted, rows


def main():
    parser = argparse.ArgumentParser(description="Add two synthetic B5 demo batches; no existing stock is reset.")
    parser.add_argument("--acknowledge-synthetic", action="store_true", required=True)
    args = parser.parse_args()
    try:
        inserted, rows = seed_b5(DomainDatabase.from_environment())
    except DomainError as error:
        print(f"B5 stock seed failed [{error.code}]; existing stock was not changed.", file=sys.stderr)
        return 1
    print(f"B5 synthetic stock: {inserted} batch(es) inserted; existing counters preserved.")
    for row in rows:
        available = row["total_qty"] - row["reserved_qty"] - row["allocated_qty"]
        print(f"{row['id']}: {row['color']}, date={row['arrives_on']}, available={available}, reserved={row['reserved_qty']}, allocated={row['allocated_qty']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
