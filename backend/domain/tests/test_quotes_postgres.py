"""Real PostgreSQL transactions/races in fresh, disposable test-owned schemas.

TEST_DATABASE_URL is deliberately separate from the application's DATABASE_URL.
All policies and negotiations here are explicitly synthetic development inputs.
"""

from concurrent.futures import ThreadPoolExecutor
import os
import re
from threading import Barrier, Event
import time
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from backend.domain import negotiation
from backend.domain.contracts import OfferAction, SellerStockBatch
from backend.domain.database import DomainDatabase, DomainError
from backend.domain.migrate import apply_migrations
from backend.domain.negotiation_fixtures import FixtureAgents, fixture_scenario
from backend.domain.quotes import QuoteAdapter


@pytest.fixture
def domain(monkeypatch):
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for actual PostgreSQL race tests")
    schema = "a3_test_" + uuid4().hex
    assert re.fullmatch(r"a3_test_[0-9a-f]{32}", schema)
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    database = DomainDatabase(dsn, schema=schema)
    try:
        assert apply_migrations(database) == 1
        # Only the fixture negotiation is simulated. All inventory, quote,
        # claim, rollback, clock, and race behavior below uses real PostgreSQL.
        monkeypatch.setattr(negotiation, "call_agent_bounded", lambda source, actor, data, timeout: getattr(source, f"generate_{actor}")(data))
        yield QuoteAdapter(database)
    finally:
        # Drop only the unique schema this fixture created, never a team schema.
        assert re.fullmatch(r"a3_test_[0-9a-f]{32}", schema)
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def agreed():
    scenario = fixture_scenario(30000)
    outcome = negotiation.run_negotiation(scenario, FixtureAgents())
    assert outcome.status == "agreed"
    return outcome, scenario


def seed(domain, scenario):
    for batch in scenario.seller.stock_batches:
        domain.add_stock_batch(scenario.seller.sku, batch)


def issue(domain, session="buyer_1", request="request_1", ttl=900):
    outcome, scenario = agreed()
    seed(domain, scenario)
    return domain.issue_quote(session, outcome, scenario, request, ttl_seconds=ttl)


def counts(domain):
    with domain.database.transaction() as connection:
        row = connection.execute("SELECT sum(total_qty) AS total, sum(reserved_qty) AS reserved, sum(allocated_qty) AS allocated FROM domain_stock_batches").fetchone()
    return tuple(int(row[name] or 0) for name in ("total", "reserved", "allocated"))


def count_rows(domain, table):
    with domain.database.transaction() as connection:
        return connection.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(table))).fetchone()["n"]


def outcome_of(function):
    try:
        return function()
    except DomainError as error:
        return error.code


def test_migration_replay_and_checksum_drift(domain):
    assert apply_migrations(domain.database) == 0
    assert count_rows(domain, "domain_schema_migrations") == 1
    with domain.database.transaction() as connection:
        connection.execute("UPDATE domain_schema_migrations SET checksum = 'test_only_drift'")
    with pytest.raises(DomainError) as caught:
        apply_migrations(domain.database)
    assert caught.value.code == "migration_conflict"


def test_quote_frozen_terms_ownership_and_idempotent_issuance(domain):
    quote = issue(domain)
    assert quote.total_cents == 35400 and quote.currency == "USD"
    assert [(line.color, line.qty, line.deliver_by.isoformat()) for line in quote.lines] == [
        ("navy", 12, "2026-11-13"), ("black", 18, "2026-11-16"),
    ]
    assert quote.expires_at.utcoffset().total_seconds() == 0
    assert "session" not in quote.model_dump_json()
    repeated = issue(domain, ttl=3600)
    assert repeated.id == quote.id and repeated.expires_at == quote.expires_at
    assert counts(domain) == (30, 30, 0) and count_rows(domain, "domain_quotes") == 1
    assert domain.get_quote("buyer_1", quote.id).id == quote.id
    with pytest.raises(DomainError) as caught:
        domain.get_quote("foreign_session", quote.id)
    assert caught.value.status_code == 404
    with pytest.raises(DomainError):
        domain.claim_for_authorization("foreign_session", quote.id, "op_foreign")
    assert counts(domain) == (30, 30, 0)


def test_two_buyers_race_for_the_final_friday_batch_exactly_one_wins(domain):
    outcome, scenario = agreed()
    seed(domain, scenario)
    barrier = Barrier(2)
    def compete(number):
        barrier.wait(timeout=5)
        return outcome_of(lambda: domain.issue_quote(f"buyer_{number}", outcome, scenario, f"request_{number}"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, (1, 2)))
    assert sum(not isinstance(result, str) for result in results) == 1
    assert results.count("stock_conflict") == 1
    assert counts(domain) == (30, 30, 0)
    assert count_rows(domain, "domain_quotes") == 1
    assert count_rows(domain, "domain_reservations") == 2


def test_unavailable_second_batch_rolls_back_first_batch(domain):
    outcome, scenario = agreed()
    domain.add_stock_batch("shirts", scenario.seller.stock_batches[0])
    domain.add_stock_batch("shirts", SellerStockBatch(batch_id="monday_black", color="black", available_qty=17, deliver_by="2026-11-16"))
    with pytest.raises(DomainError) as caught:
        domain.issue_quote("buyer", outcome, scenario, "issue_rollback")
    assert caught.value.code == "stock_conflict"
    assert counts(domain) == (29, 0, 0)
    assert count_rows(domain, "domain_quotes") == 0
    assert count_rows(domain, "domain_reservations") == 0
    assert next(batch for batch in domain.inventory_snapshot("shirts") if batch.batch_id == "friday_navy").available_qty == 12


def test_repeated_release_restores_stock_once_and_cancels_quote(domain):
    quote = issue(domain)
    assert domain.claim_for_authorization("buyer_1", quote.id, "op_1").state == "claimed"
    domain.release_claim("op_1")
    domain.release_claim("op_1")
    assert counts(domain) == (30, 0, 0)
    assert sum(batch.available_qty for batch in domain.inventory_snapshot("shirts")) == 30
    for callback in (
        lambda: domain.claim_for_authorization("buyer_1", quote.id, "op_1"),
        lambda: domain.claim_for_authorization("buyer_1", quote.id, "op_2"),
        lambda: domain.commit_allocation("op_1"),
    ):
        with pytest.raises(DomainError) as caught:
            callback()
        assert caught.value.code == "operation_conflict"
    replacement = issue(domain, request="new_issue")
    with pytest.raises(DomainError) as caught:
        domain.claim_for_authorization("buyer_1", replacement.id, "op_1")
    assert caught.value.code == "operation_conflict"


def test_commit_is_idempotent_and_release_after_commit_never_restocks(domain):
    quote = issue(domain)
    domain.claim_for_authorization("buyer_1", quote.id, "op_1")
    domain.commit_allocation("op_1")
    domain.commit_allocation("op_1")
    domain.release_claim("op_1")
    assert counts(domain) == (30, 0, 30)
    assert domain.get_quote("buyer_1", quote.id).state == "allocated"
    assert domain.claim_for_authorization("buyer_1", quote.id, "op_1").state == "allocated"


def test_pending_claim_survives_new_adapter_and_expiry(domain):
    quote = issue(domain, ttl=1)
    domain.claim_for_authorization("buyer_1", quote.id, "pending_op")
    time.sleep(1.1)
    restarted = QuoteAdapter(domain.database)
    assert restarted.recover_expired() == 0
    assert restarted.get_quote("buyer_1", quote.id).state == "claimed"
    assert restarted.claim_for_authorization("buyer_1", quote.id, "pending_op").state == "claimed"
    assert counts(domain) == (30, 30, 0)
    with pytest.raises(DomainError):
        restarted.claim_for_authorization("buyer_1", quote.id, "different_op")
    with pytest.raises(DomainError):
        restarted.release_quote("buyer_1", quote.id)
    restarted.commit_allocation("pending_op")
    assert counts(domain) == (30, 0, 30)


def test_lazy_expiry_commits_recovery_even_though_get_raises(domain):
    quote = issue(domain, ttl=1)
    time.sleep(1.1)
    for callback in (
        lambda: domain.get_quote("buyer_1", quote.id),
        lambda: domain.claim_for_authorization("buyer_1", quote.id, "late_op"),
        lambda: issue(domain),
    ):
        with pytest.raises(DomainError) as caught:
            callback()
        assert caught.value.status_code == 410
    assert counts(domain) == (30, 0, 0)
    assert domain.recover_expired() == 0


def test_concurrent_expiry_workers_do_not_double_release(domain):
    issue(domain, ttl=1)
    time.sleep(1.1)
    barrier = Barrier(2)
    def expire(_):
        barrier.wait(timeout=5)
        return domain.recover_expired()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(expire, (1, 2))) == [0, 1]
    assert counts(domain) == (30, 0, 0)


def test_claim_rechecks_real_clock_after_waiting_for_quote_lock(domain):
    quote = issue(domain, ttl=1)
    entered = Event()
    def claim():
        entered.set()
        return outcome_of(lambda: domain.claim_for_authorization("buyer_1", quote.id, "late_claim"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with domain.database.connect() as connection:
            connection.execute("SELECT id FROM domain_quotes WHERE id = %s FOR UPDATE", (quote.id,))
            future = pool.submit(claim)
            assert entered.wait(timeout=5)
            time.sleep(1.1)
        assert future.result(timeout=5) == "expired"
    assert counts(domain) == (30, 0, 0)


@pytest.mark.parametrize("same_operation", [True, False])
def test_concurrent_claims_are_idempotent_or_conflicting(domain, same_operation):
    quote = issue(domain)
    barrier = Barrier(2)
    def claim(number):
        barrier.wait(timeout=5)
        operation = "same_op" if same_operation else f"op_{number}"
        return outcome_of(lambda: domain.claim_for_authorization("buyer_1", quote.id, operation))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, (1, 2)))
    assert sum(not isinstance(result, str) for result in results) == (2 if same_operation else 1)
    if not same_operation:
        assert results.count("operation_conflict") == 1
    assert count_rows(domain, "domain_authorization_claims") == 1
    assert counts(domain) == (30, 30, 0)


def test_concurrent_duplicate_issuance_returns_one_reservation(domain):
    outcome, scenario = agreed()
    seed(domain, scenario)
    barrier = Barrier(2)
    def create(_):
        barrier.wait(timeout=5)
        return domain.issue_quote("buyer", outcome, scenario, "same_issue")
    with ThreadPoolExecutor(max_workers=2) as pool:
        quotes = list(pool.map(create, (1, 2)))
    assert quotes[0].id == quotes[1].id
    assert counts(domain) == (30, 30, 0) and count_rows(domain, "domain_quotes") == 1


def test_concurrent_commit_and_release_have_one_terminal_outcome(domain):
    quote = issue(domain)
    domain.claim_for_authorization("buyer_1", quote.id, "op_race")
    barrier = Barrier(2)
    def finish(commit):
        barrier.wait(timeout=5)
        return outcome_of(lambda: domain.commit_allocation("op_race") if commit else domain.release_claim("op_race"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finish, (True, False)))
    assert all(result in (None, "operation_conflict") for result in results)
    assert counts(domain) in ((30, 0, 30), (30, 0, 0))
    with domain.database.transaction() as connection:
        states = connection.execute("SELECT q.state AS quote_state, c.state AS claim_state FROM domain_quotes q JOIN domain_authorization_claims c ON c.quote_id = q.id").fetchone()
    assert (states["quote_state"], states["claim_state"]) in (("allocated", "committed"), ("released", "released"))


@pytest.mark.parametrize("column,value", [("total_cents", 1), ("session_id", "foreign"), ("expires_at", "2099-01-01T00:00:00Z"), ("lines", '[]')])
def test_database_rejects_term_changes(domain, column, value):
    quote = issue(domain)
    with pytest.raises(psycopg.errors.CheckViolation):
        with domain.database.connect() as connection:
            connection.execute(sql.SQL("UPDATE domain_quotes SET {} = %s WHERE id = %s").format(sql.Identifier(column)), (value, quote.id))
    assert domain.get_quote("buyer_1", quote.id).total_cents == 35400


@pytest.mark.parametrize("column,value", [("reserved_qty", -1), ("reserved_qty", 13), ("allocated_qty", 13)])
def test_database_constraints_prevent_negative_or_excess_stock(domain, column, value):
    _, scenario = agreed()
    seed(domain, scenario)
    with pytest.raises(psycopg.errors.CheckViolation):
        with domain.database.connect() as connection:
            connection.execute(sql.SQL("UPDATE domain_stock_batches SET {} = %s WHERE id = 'friday_navy'").format(sql.Identifier(column)), (value,))
    assert counts(domain) == (30, 0, 0)


def test_reseed_never_overwrites_an_active_reservation(domain):
    issue(domain)
    _, scenario = agreed()
    seed(domain, scenario)
    assert counts(domain) == (30, 30, 0)
    with pytest.raises(DomainError):
        domain.add_stock_batch("shirts", scenario.seller.stock_batches[0].model_copy(update={"available_qty": 99}))
    assert counts(domain) == (30, 30, 0)


def test_same_request_identifier_cannot_change_owner_or_terms(domain):
    quote = issue(domain)
    outcome, scenario = agreed()
    with pytest.raises(DomainError) as caught:
        domain.issue_quote("other_buyer", outcome, scenario, "request_1")
    assert caught.value.code == "not_found"
    revised = outcome.agreement.model_copy(update={"total_cents": 35500})
    events = list(outcome.events)
    events[1] = events[1].model_copy(update={"action": OfferAction(type="offer", terms=revised)})
    different = outcome.model_copy(update={"agreement": revised, "events": tuple(events)})
    with pytest.raises(DomainError) as caught:
        domain.issue_quote("buyer_1", different, scenario, "request_1")
    assert caught.value.code == "idempotency_conflict"
    assert domain.get_quote("buyer_1", quote.id).total_cents == 35400


def test_release_unclaimed_is_idempotent(domain):
    quote = issue(domain)
    domain.release_quote("buyer_1", quote.id)
    domain.release_quote("buyer_1", quote.id)
    assert counts(domain) == (30, 0, 0)


def test_same_operation_cannot_claim_two_quotes(domain):
    first = issue(domain)
    domain.claim_for_authorization("buyer_1", first.id, "op_stable")
    domain.release_claim("op_stable")
    second = issue(domain, request="second_issue")
    with pytest.raises(DomainError) as caught:
        domain.claim_for_authorization("buyer_1", second.id, "op_stable")
    assert caught.value.code == "operation_conflict"


def test_shortfall_negotiation_cannot_issue_any_quote(domain):
    scenario = fixture_scenario(30000, shortfall=True)
    seed(domain, scenario)
    no_deal = negotiation.run_negotiation(scenario, FixtureAgents())
    with pytest.raises(DomainError) as caught:
        domain.issue_quote("buyer", no_deal, scenario, "shortfall_issue")
    assert caught.value.code == "invalid_agreement"
    assert counts(domain) == (26, 0, 0)
    assert count_rows(domain, "domain_quotes") == 0


def test_unknown_operations_have_safe_errors(domain):
    for callback in (domain.commit_allocation, domain.release_claim):
        with pytest.raises(DomainError) as caught:
            callback("unknown_operation")
        assert caught.value.status_code == 404


def test_release_of_expired_pending_claim_restores_once(domain):
    quote = issue(domain, ttl=1)
    domain.claim_for_authorization("buyer_1", quote.id, "held_op")
    time.sleep(1.1)
    domain.release_claim("held_op")
    domain.release_claim("held_op")
    assert counts(domain) == (30, 0, 0)
    with pytest.raises(DomainError) as caught:
        domain.get_quote("buyer_1", quote.id)
    assert caught.value.status_code == 410


def test_payment_migration_can_follow_domain_migration(domain):
    from pathlib import Path
    script = (Path(__file__).resolve().parents[2] / "payments" / "migrations" / "001_payments.sql").read_text(encoding="utf-8")
    # Source file is read only. DDL is applied solely in this test-owned schema.
    with domain.database.transaction() as connection:
        connection.execute(script, prepare=False)
    assert count_rows(domain, "payment_operations") == 0
    assert issue(domain).total_cents == 35400
