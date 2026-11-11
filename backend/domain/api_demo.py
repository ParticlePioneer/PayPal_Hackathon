"""Terminal-only A4 demonstration using synthetic policy and an isolated schema.

Requires TEST_DATABASE_URL pointing to a disposable PostgreSQL database. Never
uses DATABASE_URL, starts no public server, and makes no provider calls.
"""

import argparse
import json
import os
import re
import sys
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
from psycopg import sql

from .api import NegotiationService, create_router
from .database import DomainDatabase
from .migrate import apply_migrations
from .negotiation_fixtures import FixtureAgents, fixture_scenario
from .quotes import QuoteAdapter


def main(argv=None):
    parser = argparse.ArgumentParser(description="Synthetic A4 HTTP/database demonstration")
    parser.add_argument("--scenario", choices=("split", "shortfall"), required=True)
    args = parser.parse_args(argv)
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        print("TEST_DATABASE_URL is required for the disposable demo database.", file=sys.stderr)
        return 1
    schema = "a4_demo_" + uuid4().hex
    created = False
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        created = True
        database = DomainDatabase(dsn, schema=schema)
        apply_migrations(database)
        quotes = QuoteAdapter(database)
        scenario = fixture_scenario(30000, shortfall=args.scenario == "shortfall")
        for batch in scenario.seller.stock_batches:
            quotes.add_stock_batch(scenario.seller.sku, batch)
        service = NegotiationService(quotes, lambda _: scenario.seller, FixtureAgents())
        app = FastAPI()
        app.include_router(create_router(service, session_dependency=lambda: "demo_buyer"))
        payload = {**scenario.buyer.requirements.model_dump(mode="json"), "budget_cents": scenario.buyer.budget_cents}
        with TestClient(app) as client:
            response = client.post("/api/negotiations", json=payload)
            response.raise_for_status()
            view = response.json()
            for _ in range(6):
                if view["status"] not in {"negotiating", "retryable_error"}:
                    break
                response = client.post(f"/api/negotiations/{view['id']}/turn", json={"expected_version": view["version"]})
                response.raise_for_status()
                view = response.json()
            response = client.get(f"/api/negotiations/{view['id']}")
            response.raise_for_status()
            view = response.json()
        print(json.dumps({"mode": "synthetic_fixture", "scenario": args.scenario, "view": view}, separators=(",", ":")))
        return 0 if view["status"] in {"quoted", "no_deal"} else 1
    except Exception:
        print("Synthetic A4 demo failed; private configuration was withheld.", file=sys.stderr)
        return 1
    finally:
        if created:
            assert re.fullmatch(r"a4_demo_[0-9a-f]{32}", schema)
            try:
                with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as connection:
                    connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            except Exception:
                raise RuntimeError("Unable to remove the test-owned demo schema.") from None


if __name__ == "__main__":
    raise SystemExit(main())
