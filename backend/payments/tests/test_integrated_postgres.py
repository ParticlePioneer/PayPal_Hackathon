"""Integration against a disposable test-owned PostgreSQL schema; no live providers."""
import os
import json
import unittest
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import psycopg
import httpx
from psycopg import sql
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.domain.fixtures import split_offer_fixture
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

    @contextmanager
    def openrouter_host(self, handler):
        """Real host/DB/adapter; HTTP provider responses are simulated, not live evidence.

        Run the agent boundary inline so the local HTTP stub is visible. Separate
        domain process tests exercise the actual spawned worker and deadline.
        """
        self.quotes.release_quote("buyer_1", self.quote.id)
        real_client = httpx.Client
        env = {
            "B4_ENABLED": "true", "SESSION_SECRET": "s" * 40,
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_MODEL": "example/test-model:free",
            "MERCHANT_MINIMUM_TOTAL_CENTS": "30000",
        }
        with patch.dict("os.environ", env, clear=True), patch.object(DomainDatabase, "from_environment", return_value=self.db), patch.object(integrated, "database", self.db.transaction), patch("backend.domain.turns.call_agent_bounded", lambda source, actor, data, timeout: getattr(source, f"generate_{actor}")(data)), patch("backend.domain.openrouter_client.httpx.Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            application = create_app()
            with TestClient(application) as client:
                yield application, client

    def start_http_negotiation(self, client):
        payload = self.scenario.buyer.requirements.model_dump(mode="json")
        payload["budget_cents"] = self.scenario.buyer.budget_cents
        response = client.post("/api/negotiations", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def advance_http_negotiation(self, client, view):
        response = client.post(f"/api/negotiations/{view['id']}/turn", json={"expected_version": view["version"]})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def completion(action):
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"action": action})}}]})

    def test_openrouter_http_quote_checkout_refresh_and_ownership(self):
        calls = []

        def respond(request):
            self.assertEqual(str(request.url), "https://openrouter.ai/api/v1/chat/completions")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "example/test-model:free")
            data = json.loads(payload["messages"][1]["content"])
            calls.append(data["role"])
            if data["role"] == "seller":
                self.assertNotIn("budget_cents", json.dumps(data))
                return self.completion({"type": "offer", "terms": split_offer_fixture().model_dump(mode="json")})
            self.assertNotIn("minimum_total_cents", json.dumps(data))
            events = data["input"]["shared"]["events"]
            return self.completion({"type": "accept", "offer_id": events[-1]["issued_offer_id"]} if events else {"type": "ask", "topic": "delivery_options"})

        auth = {"purchase_units": [{"payments": {"authorizations": [{"id": "auth-http", "status": "CREATED", "amount": {"currency_code": "USD", "value": "354.00"}}]}}]}
        with self.openrouter_host(respond) as (application, client), patch.object(provider, "create_order", return_value={"id": "order-http"}) as create, patch.object(provider, "authorize_order", return_value=auth) as authorize:
            view = self.start_http_negotiation(client)
            for _ in range(3):
                view = self.advance_http_negotiation(client, view)
            self.assertEqual(view["status"], "quoted")
            self.assertEqual(view["quote"]["total_cents"], 35400)
            quote_id = view["quote"]["id"]
            create.assert_not_called()
            status_url = f"/api/payments/quotes/{quote_id}"
            self.assertEqual(client.get(status_url).json()["operations"], [])
            other = TestClient(application)
            self.assertEqual(other.get(f"/api/negotiations/{view['id']}").status_code, 404)
            self.assertEqual(other.get(status_url).status_code, 404)
            self.assertEqual(other.post("/api/payments/orders", json={"quote_id": quote_id}, headers={"Origin": "http://testserver"}).status_code, 404)
            other.close()
            create.assert_not_called()
            order = client.post("/api/payments/orders", json={"quote_id": quote_id}, headers={"Origin": "http://testserver"})
            self.assertEqual(order.status_code, 200, order.text)
            url = f"/api/payments/orders/{order.json()['id']}/authorize"
            first = client.post(url, headers={"Origin": "http://testserver"})
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()["authorization_id"], "auth-http")
            self.assertEqual(client.post(url, headers={"Origin": "http://testserver"}).json(), first.json())
            self.assertEqual(client.get(f"/api/negotiations/{view['id']}").json(), view)
            operations = client.get(status_url).json()["operations"]
            self.assertTrue(any(op["paypal_authorization_id"] == "auth-http" and op["status"] == "succeeded" for op in operations))
            self.assertEqual(create.call_args.args[0], 35400)
            self.assertEqual(create.call_count, 1)
            self.assertEqual(authorize.call_count, 1)
        self.assertEqual(calls, ["buyer", "seller", "buyer"])

    def test_openrouter_errors_and_no_deal_create_no_payment(self):
        response = [httpx.Response(503, json={"error": "private-provider-body"})]
        with self.openrouter_host(lambda _: response[0]) as (_, client), patch.object(provider, "create_order") as create, patch.object(provider, "authorize_order") as authorize:
            view = self.start_http_negotiation(client)
            for status in (429, 503, 504, 200):
                with self.subTest(status=status):
                    response[0] = httpx.Response(status, json={"error": "private-provider-body"})
                    view = self.advance_http_negotiation(client, view)
                    self.assertEqual(view["status"], "retryable_error")
                    self.assertIsNone(view["quote"])
                    self.assertEqual(view["messages"], [])
                    self.assertNotIn("private-provider-body", json.dumps(view))
                    self.assertEqual(client.get(f"/api/negotiations/{view['id']}").json(), view)
            response[0] = self.completion({"type": "decline", "reason_code": "terms_unacceptable"})
            view = self.advance_http_negotiation(client, view)
            self.assertEqual(view["status"], "no_deal")
            self.assertIsNone(view["quote"])
            self.assertEqual(client.post("/api/payments/orders", json={"quote_id": "q_absent"}, headers={"Origin": "http://testserver"}).status_code, 404)
            create.assert_not_called()
            authorize.assert_not_called()
            with self.db.transaction() as conn:
                self.assertEqual(conn.execute("SELECT count(*) AS n FROM payment_operations").fetchone()["n"], 0)
                self.assertEqual(conn.execute("SELECT count(*) AS n FROM domain_quotes WHERE state <> 'released'").fetchone()["n"], 0)


if __name__ == "__main__":
    unittest.main()
