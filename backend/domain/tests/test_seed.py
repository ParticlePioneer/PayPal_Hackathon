"""A6 seed validation and real PostgreSQL safety checks."""

from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
from threading import Barrier
from unittest.mock import MagicMock

import pytest

from backend.domain import seed
from backend.domain.contracts import SellerStockBatch
from backend.domain.database import DomainError
from backend.domain.negotiation_fixtures import fixture_scenario
from backend.domain.tests.test_quotes_postgres import domain, agreed, counts


@pytest.mark.parametrize("scenario,expected", [("split", 30), ("shortfall", 26)])
def test_clean_database_seeds_once_and_replay_is_noop(domain, scenario, expected):
    assert seed.seed_fixture(domain.database, scenario) == 2
    assert counts(domain) == (expected, 0, 0)
    expected_batches = sorted(fixture_scenario(30000, shortfall=scenario == "shortfall").seller.stock_batches, key=lambda batch: batch.batch_id)
    assert domain.inventory_snapshot("shirts") == tuple(expected_batches)
    assert seed.seed_fixture(domain.database, scenario) == 0
    assert counts(domain) == (expected, 0, 0)


def test_reseed_preserves_active_reservation_and_pending_claim(domain):
    assert seed.seed_fixture(domain.database, "split") == 2
    outcome, scenario = agreed()
    quote = domain.issue_quote("buyer", outcome, scenario, "seed_test")
    domain.claim_for_authorization("buyer", quote.id, "pending_seed_test")
    assert counts(domain) == (30, 30, 0)
    assert seed.seed_fixture(domain.database, "split") == 0
    assert counts(domain) == (30, 30, 0)
    assert domain.claim_for_authorization("buyer", quote.id, "pending_seed_test").state == "claimed"


def test_conflicting_batch_aborts_without_inserting_missing_batch(domain):
    domain.add_stock_batch("shirts", SellerStockBatch(batch_id="friday_navy", color="navy", available_qty=99, deliver_by="2026-11-13"))
    with pytest.raises(DomainError) as caught:
        seed.seed_fixture(domain.database, "split")
    assert caught.value.code == "stock_conflict" and counts(domain) == (99, 0, 0)
    assert [batch.batch_id for batch in domain.inventory_snapshot("shirts")] == ["friday_navy"]


def test_switching_scenario_does_not_replace_stock(domain):
    seed.seed_fixture(domain.database, "split")
    with pytest.raises(DomainError) as caught:
        seed.seed_fixture(domain.database, "shortfall")
    assert caught.value.code == "stock_conflict" and counts(domain) == (30, 0, 0)


def test_concurrent_identical_seed_is_idempotent(domain):
    barrier = Barrier(2)
    def run(_):
        barrier.wait(timeout=5)
        return seed.seed_fixture(domain.database, "split")
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, (1, 2))) == [0, 2]
    assert counts(domain) == (30, 0, 0)


@pytest.mark.parametrize("value", [None, "", "production", True, []])
def test_invalid_scenario_never_opens_a_connection(value):
    database = MagicMock()
    with pytest.raises(DomainError) as caught:
        seed.seed_fixture(database, value)
    assert caught.value.code == "invalid_input"
    database.transaction.assert_not_called()


def test_cli_requires_explicit_synthetic_acknowledgement(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(seed.DomainDatabase, "from_environment", factory)
    with pytest.raises(SystemExit) as caught:
        seed.main(["--scenario", "split"])
    assert caught.value.code == 2
    factory.assert_not_called()


def test_cli_reports_sanitized_storage_error(monkeypatch, capsys):
    monkeypatch.setattr(seed.DomainDatabase, "from_environment", MagicMock(side_effect=DomainError("storage_unavailable")))
    assert seed.main(["--scenario", "split", "--acknowledge-synthetic"]) == 1
    captured = capsys.readouterr()
    assert not captured.out and "storage_unavailable" in captured.err


def test_seed_can_import_without_google_sdk():
    command = "import sys; sys.modules['google'] = None; import backend.domain.seed; print('ok')"
    result = subprocess.run([sys.executable, "-B", "-c", command], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0 and result.stdout.strip() == "ok"
