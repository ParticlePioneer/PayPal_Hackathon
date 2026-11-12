"""Rehearse migrations and demo seeding in a disposable PostgreSQL schema."""
import os
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from backend.domain.database import DomainDatabase
from backend.domain.migrate import apply_migrations
from backend.domain.seed import seed_fixture
from backend.payments.migrate import apply as apply_payments


def main():
    dsn = os.getenv("TEST_DATABASE_URL", "")
    if not dsn:
        print("TEST_DATABASE_URL is required and must point to a disposable database.", file=sys.stderr)
        return 1
    schema = "b5_clean_" + uuid4().hex
    created = False
    passed = False
    cleaned = False
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        created = True
        domain = DomainDatabase(dsn, schema=schema)
        domain_count = apply_migrations(domain)
        payment_dsn = make_conninfo(dsn, options=f"-c search_path={schema}")
        payment_count = apply_payments(payment_dsn)
        first_seed = seed_fixture(domain, "split")
        repeat_domain = apply_migrations(domain)
        repeat_payments = apply_payments(payment_dsn)
        repeat_seed = seed_fixture(domain, "split")
        if (domain_count < 1 or payment_count < 3 or first_seed != 2 or
                repeat_domain != 0 or repeat_payments != 0 or repeat_seed != 0):
            raise RuntimeError("Unexpected migration or seed counts")
        print(f"Clean schema: domain migrations={domain_count}, payment migrations={payment_count}, seeded batches={first_seed}.")
        print("Repeat: domain migrations=0, payment migrations=0, seeded batches=0.")
        passed = True
    except Exception:
        print("Clean-install database check failed; private database details were withheld.", file=sys.stderr)
    finally:
        if created:
            try:
                with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as conn:
                    conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
                cleaned = True
            except Exception:
                # The random identifier contains no secrets and lets an owner
                # remove this test-owned schema if cleanup is interrupted.
                print(f"Cleanup failed for test schema {schema}.", file=sys.stderr)
    if passed and cleaned:
        print("Clean-install database check PASSED; test schema removed.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
