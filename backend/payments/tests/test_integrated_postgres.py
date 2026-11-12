"""Integration against a disposable test-owned PostgreSQL schema; no live providers."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from fastapi import HTTPException
from backend.domain import negotiation
from backend.domain.database import DomainDatabase
from backend.domain.migrate import apply_migrations
from backend.domain.negotiation_fixtures import FixtureAgents, fixture_scenario
from backend.domain.quotes import QuoteAdapter
from backend.payments import integrated, provider


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is required for PostgreSQL integration")
class IntegratedPostgresTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ["TEST_DATABASE_URL"]
        self.schema = "b4_test_" + uuid4().hex
        with psycopg.connect(self.dsn, autocommit=True, connect_timeout=5) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        self.db = DomainDatabase(self.dsn, schema=self.schema)
        apply_migrations(self.db)
        with self.db.transaction() as conn:
            for filename in ("001_payments.sql", "002_b2_harness.sql"):
                script = (Path(__file__).parents[1] / "migrations" / filename).read_text(encoding="utf-8-sig")
                conn.execute(script, prepare=False)
        self.quotes = QuoteAdapter(self.db)
        self.scenario = fixture_scenario(30000)
        for batch in self.scenario.seller.stock_batches:
            self.quotes.add_stock_batch(self.scenario.seller.sku, batch)
        with patch.object(negotiation, "call_agent_bounded", lambda source, actor, data, timeout: getattr(source, f"generate_{actor}")(data)):
            result = negotiation.run_negotiation(self.scenario, FixtureAgents())
        self.quote = self.quotes.issue_quote("buyer_1", result, self.scenario, "issue_1")
        self.request = SimpleNamespace(state=SimpleNamespace(session_id="buyer_1"), headers={"origin": "https://example.test", "host": "example.test"})

    def drop_schema(self):
        with psycopg.connect(self.dsn, autocommit=True, connect_timeout=5) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def test_quote_amount_authorization_and_duplicate(self):
        response = {"purchase_units": [{"payments": {"authorizations": [{"id": "auth-1", "status": "CREATED", "amount": {"currency_code": "USD", "value": "354.00"}}]}}]}
        with patch.object(integrated, "database", self.db.transaction), patch.object(integrated, "adapter", return_value=self.quotes), patch.object(provider, "create_order", return_value={"id": "order-1"}) as create, patch.object(provider, "authorize_order", return_value=response) as authorize:
            self.assertEqual(integrated.create_order(self.quote.id, self.request)["id"], "order-1")
            first = integrated.authorize("order-1", self.request)
            second = integrated.authorize("order-1", self.request)
        self.assertEqual(first, second)
        self.assertEqual(create.call_args.args[0], 35400)
        self.assertEqual(authorize.call_count, 1)
        self.assertEqual(self.quotes.get_quote("buyer_1", self.quote.id).state, "allocated")

    def test_foreign_session_cannot_create_order(self):
        other = SimpleNamespace(state=SimpleNamespace(session_id="buyer_2"), headers=self.request.headers)
        with patch.object(integrated, "database", self.db.transaction), patch.object(integrated, "adapter", return_value=self.quotes), patch.object(provider, "create_order") as create:
            with self.assertRaises(HTTPException) as error:
                integrated.create_order(self.quote.id, other)
        self.assertEqual(error.exception.status_code, 404)
        create.assert_not_called()

    def test_unknown_authorization_keeps_claim_and_blocks_replay(self):
        with patch.object(integrated, "database", self.db.transaction), patch.object(integrated, "adapter", return_value=self.quotes), patch.object(provider, "create_order", return_value={"id": "order-1"}), patch.object(provider, "authorize_order", side_effect=provider.ProviderError("timeout")) as authorize:
            integrated.create_order(self.quote.id, self.request)
            with self.assertRaises(HTTPException) as first:
                integrated.authorize("order-1", self.request)
            with self.assertRaises(HTTPException) as duplicate:
                integrated.authorize("order-1", self.request)
        self.assertEqual(first.exception.status_code, 503)
        self.assertEqual(duplicate.exception.status_code, 409)
        self.assertEqual(authorize.call_count, 1)
        self.assertEqual(self.quotes.get_quote("buyer_1", self.quote.id).state, "claimed")
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status FROM payment_operations WHERE quote_id = %s AND operation_type = 'authorize'", (self.quote.id,)).fetchone()
        self.assertEqual(row["status"], "unknown")

    def test_concurrent_duplicate_orders_make_at_most_one_provider_call(self):
        with patch.object(integrated, "database", self.db.transaction), patch.object(integrated, "adapter", return_value=self.quotes), patch.object(provider, "create_order", return_value={"id": "order-1"}) as create:
            def attempt():
                try:
                    return integrated.create_order(self.quote.id, self.request)
                except HTTPException as exc:
                    return exc.status_code
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(lambda _: attempt(), range(2)))
        self.assertEqual(create.call_count, 1)
        self.assertIn({"id": "order-1"}, results)
        self.assertTrue(all(value == 409 or value == {"id": "order-1"} for value in results))


if __name__ == "__main__":
    unittest.main()
