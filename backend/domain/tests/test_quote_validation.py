"""Pure input/security checks; no database or provider connection is needed."""

from unittest.mock import MagicMock

import psycopg
import pytest

from backend.domain.database import DomainDatabase, DomainError
from backend.domain import migrate
from backend.domain.quotes import QuoteAdapter


@pytest.mark.parametrize("schema", ["public;DROP SCHEMA public", "a b", "A", "1bad", "x" * 64, None, True])
def test_schema_identifier_cannot_inject_options(schema):
    with pytest.raises(DomainError):
        DomainDatabase("postgresql://localhost/test", schema=schema)


def test_database_errors_hide_connection_details(monkeypatch):
    monkeypatch.setattr("backend.domain.database.psycopg.connect", MagicMock(side_effect=psycopg.OperationalError("private_password_marker")))
    database = DomainDatabase("postgresql://fake:private_dsn@localhost/test")
    with pytest.raises(DomainError) as caught:
        with database.transaction():
            pass
    assert caught.value.code == "storage_unavailable"
    assert "private_password_marker" not in str(caught.value)
    assert "private_dsn" not in repr(database)
    assert caught.value.__suppress_context__ is True


@pytest.mark.parametrize("value", [None, "", "has space", "x" * 129, 1, True, "id;SELECT"])
def test_invalid_ids_never_open_a_database_connection(value):
    database = MagicMock()
    adapter = QuoteAdapter(database)
    for action in (
        lambda: adapter.get_quote(value, "quote"),
        lambda: adapter.get_quote("session", value),
        lambda: adapter.claim_for_authorization("session", "quote", value),
        lambda: adapter.commit_allocation(value),
        lambda: adapter.release_claim(value),
    ):
        with pytest.raises(DomainError) as caught:
            action()
        assert caught.value.code == "invalid_input"
    database.transaction.assert_not_called()


@pytest.mark.parametrize("limit", [0, -1, True, "100", 1001])
def test_recovery_limit_validation(limit):
    database = MagicMock()
    with pytest.raises(DomainError):
        QuoteAdapter(database).recover_expired(limit=limit)
    database.transaction.assert_not_called()


def test_missing_database_configuration_is_sanitized(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(DomainError):
        DomainDatabase.from_environment()


def test_domain_environment_does_not_mutate_process_or_print_secrets(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = tmp_path / "test.env"
    path.write_text("DATABASE_URL=postgresql://localhost/local_test_db\nGEMINI_API_KEY=private_marker\n", encoding="utf-8")
    database = DomainDatabase.from_environment(env_file=path)
    assert "private_marker" not in repr(database)
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(DomainError):
        DomainDatabase.from_environment(env_file=path)


def test_migration_cli_reports_static_error_not_dsn(monkeypatch, capsys):
    monkeypatch.setattr(migrate.DomainDatabase, "from_environment", MagicMock(side_effect=DomainError("storage_unavailable")))
    assert migrate.main([]) == 1
    captured = capsys.readouterr()
    assert not captured.out and "storage_unavailable" in captured.err


@pytest.mark.parametrize("dsn", ["", " ", "dbname=ambient", "sqlite:///db", "postgresql://localhost", "postgresql:///test", "postgresql://localhost:notaport/test", None, True])
def test_database_url_requires_explicit_postgres_host_and_database(dsn):
    with pytest.raises(DomainError) as caught:
        DomainDatabase(dsn)
    assert caught.value.code == "invalid_input"


def test_stock_bigint_overflow_rejected_without_connecting():
    from backend.domain.contracts import SellerStockBatch
    database = MagicMock()
    adapter = QuoteAdapter(database)
    batch = SellerStockBatch(batch_id="oversized", color="navy", available_qty=2**63, deliver_by="2026-11-13")
    with pytest.raises(DomainError) as caught:
        adapter.add_stock_batch("shirts", batch)
    assert caught.value.code == "invalid_input"
    database.transaction.assert_not_called()


@pytest.mark.parametrize("ttl", [0, -1, 3601, True, "900", None])
def test_invalid_quote_ttl_never_opens_a_connection(ttl):
    database = MagicMock()
    with pytest.raises(DomainError) as caught:
        QuoteAdapter(database).issue_quote("session", None, None, "request", ttl_seconds=ttl)
    assert caught.value.code == "invalid_input"
    database.transaction.assert_not_called()


@pytest.mark.parametrize("outcome", [None, {}, {"status": "agreed", "agreement": {"total_cents": 35400}}])
def test_raw_or_incomplete_agreements_cannot_create_quotes(outcome):
    from backend.domain.negotiation_fixtures import fixture_scenario
    database = MagicMock()
    with pytest.raises(DomainError) as caught:
        QuoteAdapter(database).issue_quote("session", outcome, fixture_scenario(30000), "request")
    assert caught.value.code == "invalid_agreement"
    database.transaction.assert_not_called()
