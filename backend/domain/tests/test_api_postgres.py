"""A4 HTTP integration with real isolated PostgreSQL and synthetic agents."""

from concurrent.futures import ThreadPoolExecutor
import os
import re
from threading import Barrier
import time
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.domain import turns
from backend.domain.api import NegotiationService, create_router
from backend.domain.database import DomainDatabase, DomainError
from backend.domain.migrate import apply_migrations
from backend.domain.negotiation_fixtures import FixtureAgents, fixture_scenario
from backend.domain.quotes import QuoteAdapter


@pytest.fixture
def environment(monkeypatch):
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL required for actual PostgreSQL integration")
    schema = "a4_test_" + uuid4().hex
    assert re.fullmatch(r"a4_test_[0-9a-f]{32}", schema)
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        database = DomainDatabase(dsn, schema=schema)
        assert apply_migrations(database) == 2
        monkeypatch.setattr(turns, "call_agent_bounded", lambda source, actor, data, timeout: getattr(source, f"generate_{actor}")(data))
        quotes = QuoteAdapter(database)
        scenario = fixture_scenario(30000)
        service = NegotiationService(quotes, lambda requirements: scenario.seller, FixtureAgents())
        app = FastAPI()
        # Test-only header simulates the host's trusted session dependency.
        def test_session(request: Request):
            return request.headers.get("X-Test-Session", "buyer_1")
        app.include_router(create_router(service, session_dependency=test_session))
        yield TestClient(app), service, scenario
    finally:
        assert re.fullmatch(r"a4_test_[0-9a-f]{32}", schema)
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def payload(scenario):
    return {**scenario.buyer.requirements.model_dump(mode="json"), "budget_cents": scenario.buyer.budget_cents}


def seed(service, scenario, *, shortfall=False):
    for batch in fixture_scenario(30000, shortfall=shortfall).seller.stock_batches:
        service.quotes.add_stock_batch(scenario.seller.sku, batch)


def create(client, scenario):
    response = client.post("/api/negotiations", json=payload(scenario))
    assert response.status_code == 200, response.text
    return response.json()


def turn(client, negotiation_id, version, **kwargs):
    return client.post(f"/api/negotiations/{negotiation_id}/turn", json={"expected_version": version}, **kwargs)


def test_success_and_refresh_produce_real_reserved_quote(environment):
    client, service, scenario = environment
    seed(service, scenario)
    view = create(client, scenario)
    assert view["status"] == "negotiating" and view["version"] == 0
    for version in range(3):
        response = turn(client, view["id"], version)
        assert response.status_code == 200, response.text
        view = response.json()
    assert view["status"] == "quoted" and view["quote"]["total_cents"] == 35400
    assert len(view["messages"]) == 3
    assert client.get(f"/api/negotiations/{view['id']}").json() == view
    assert all(word not in str(view) for word in ("budget_cents", "minimum_total_cents", "friday_navy", "session"))
    assert sum(batch.available_qty for batch in service.quotes.inventory_snapshot("shirts")) == 0
    with pytest.raises(DomainError):
        service.quotes.claim_for_authorization("foreign", view["quote"]["id"], "op_foreign")


def test_shortfall_explains_four_shirts_and_issues_no_quote(environment):
    client, service, scenario = environment
    seed(service, scenario, shortfall=True)
    view = create(client, scenario)
    for version in range(2):
        view = turn(client, view["id"], version).json()
    assert view["status"] == "no_deal" and view["quote"] is None
    assert "4 more shirts" in view["reason"]
    with service.database.transaction() as conn:
        assert conn.execute("SELECT count(*) AS n FROM domain_quotes").fetchone()["n"] == 0


def test_stock_conflict_returns_409_and_preserves_no_deal_view(environment):
    client, service, scenario = environment
    seed(service, scenario)
    first = create(client, scenario)
    second = create(client, scenario)
    for version in range(2):
        assert turn(client, first["id"], version).status_code == 200
        assert turn(client, second["id"], version).status_code == 200
    assert turn(client, first["id"], 2).json()["status"] == "quoted"
    conflict = turn(client, second["id"], 2)
    assert conflict.status_code == 409 and conflict.json()["detail"]["code"] == "stock_conflict"
    restored = client.get(f"/api/negotiations/{second['id']}").json()
    assert restored["status"] == "no_deal" and restored["quote"] is None


def test_duplicate_turn_concurrently_saves_one_event(environment, monkeypatch):
    client, service, scenario = environment
    seed(service, scenario)
    view = create(client, scenario)
    barrier = Barrier(2)
    def call(source, actor, data, timeout):
        barrier.wait(timeout=5)
        return getattr(source, f"generate_{actor}")(data)
    monkeypatch.setattr(turns, "call_agent_bounded", call)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: turn(client, view["id"], 0), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    restored = client.get(f"/api/negotiations/{view['id']}").json()
    assert restored["version"] == 1 and len(restored["messages"]) == 1


def test_recovery_after_quote_created_before_negotiation_update(environment, monkeypatch):
    client, service, scenario = environment
    seed(service, scenario)
    view = create(client, scenario)
    for version in range(2):
        view = turn(client, view["id"], version).json()
    original = service.quotes.issue_quote
    def lose_response(*args, **kwargs):
        original(*args, **kwargs)
        raise DomainError("storage_unavailable")
    monkeypatch.setattr(service.quotes, "issue_quote", lose_response)
    assert turn(client, view["id"], 2).status_code == 503
    monkeypatch.setattr(service.quotes, "issue_quote", original)
    restored = client.get(f"/api/negotiations/{view['id']}").json()
    assert restored["status"] == "quoted" and restored["version"] == 3
    with service.database.transaction() as conn:
        assert conn.execute("SELECT count(*) AS n FROM domain_quotes").fetchone()["n"] == 1
        assert conn.execute("SELECT sum(reserved_qty) AS n FROM domain_stock_batches").fetchone()["n"] == 30


def test_real_spawned_fixture_agents_work_through_http(environment, monkeypatch):
    from backend.domain.agent_process import call_agent_bounded
    client, service, scenario = environment
    seed(service, scenario)
    monkeypatch.setattr(turns, "call_agent_bounded", call_agent_bounded)
    view = create(client, scenario)
    for version in range(3):
        response = turn(client, view["id"], version)
        assert response.status_code == 200, response.text
        view = response.json()
    assert view["status"] == "quoted" and view["quote"]["total_cents"] == 35400


def test_router_default_requires_trusted_session(environment):
    _, service, scenario = environment
    app = FastAPI()
    app.include_router(create_router(service))
    response = TestClient(app).post("/api/negotiations", json=payload(scenario), headers={"X-Test-Session": "spoofed"})
    assert response.status_code == 401


def test_turn_version_is_strict_and_private_input_not_echoed(environment):
    client, service, scenario = environment
    seed(service, scenario)
    view = create(client, scenario)
    for value in (True, -1, "0"):
        response = turn(client, view["id"], value)
        assert response.status_code == 422 and "expected_version" not in response.text
    assert client.get(f"/api/negotiations/{view['id']}").json()["version"] == 0


def test_model_failure_is_retryable_without_saving_an_action(environment, monkeypatch):
    from backend.domain.model_client import ModelCallError
    client, service, scenario = environment
    seed(service, scenario)
    view = create(client, scenario)
    def unavailable(*args):
        raise ModelCallError("provider_unavailable")
    monkeypatch.setattr(turns, "call_agent_bounded", unavailable)
    failed = turn(client, view["id"], 0).json()
    assert failed["status"] == "retryable_error" and failed["version"] == 1 and failed["messages"] == []
    monkeypatch.setattr(turns, "call_agent_bounded", lambda source, actor, data, timeout: getattr(source, f"generate_{actor}")(data))
    retried = turn(client, view["id"], 1).json()
    assert retried["status"] == "negotiating" and retried["version"] == 2 and len(retried["messages"]) == 1


def test_oversized_request_has_sanitized_error(environment):
    client, _, _ = environment
    response = client.post("/api/negotiations", content=b"x" * 131073)
    assert response.status_code == 422 and "Invalid negotiation input" in response.text


def test_foreign_session_cannot_read_or_advance(environment):
    client, service, scenario = environment
    seed(service, scenario)
    view = create(client, scenario)
    headers = {"X-Test-Session": "foreign"}
    assert client.get(f"/api/negotiations/{view['id']}", headers=headers).status_code == 404
    assert turn(client, view["id"], 0, headers=headers).status_code == 404


def test_expired_quote_cannot_be_claimed_and_refresh_shows_expiry(environment, monkeypatch):
    client, service, scenario = environment
    seed(service, scenario)
    original = service.quotes.issue_quote
    monkeypatch.setattr(service.quotes, "issue_quote", lambda *args, **kwargs: original(*args, **kwargs, ttl_seconds=1))
    view = create(client, scenario)
    for version in range(3):
        view = turn(client, view["id"], version).json()
    quote_id = view["quote"]["id"]
    time.sleep(1.1)
    with pytest.raises(DomainError) as caught:
        service.quotes.claim_for_authorization("buyer_1", quote_id, "late_op")
    assert caught.value.status_code == 410
    refreshed = client.get(f"/api/negotiations/{view['id']}").json()
    assert refreshed["status"] == "expired" and refreshed["quote"] is None


@pytest.mark.parametrize("patch", [{"budget_cents": -1}, {"quantity": 0}, {"allowed_colors": ["red"]}, {"minimum_by_date": "bad"}])
def test_invalid_input_does_not_echo_private_values(environment, patch):
    client, _, scenario = environment
    response = client.post("/api/negotiations", json={**payload(scenario), **patch})
    assert response.status_code == 422
    assert "budget_cents" not in response.text and "36000" not in response.text
